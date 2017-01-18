#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import copy
import os
import yaml

from translator.hot.syntax.hot_resource import HotResource

# Name used to dynamically load appropriate map class.
TARGET_CLASS_NAME = 'ToscaAutoscaling'
HEAT_TEMPLATE_BASE = """
heat_template_version: 2013-05-23
"""
ALARM_STATISTIC = {'average': 'avg'}
SCALING_RESOURCES = ["OS::Heat::ScalingPolicy", "OS::Heat::AutoScalingGroup",
                     "OS::Aodh::Alarm"]


class ToscaAutoscaling(HotResource):
    '''Translate TOSCA node type tosca.policies.Scaling'''

    toscatype = 'tosca.policies.Scaling'

    def __init__(self, policy, csar_dir=None):
        hot_type = "OS::Heat::ScalingPolicy"
        super(ToscaAutoscaling, self).__init__(policy,
                                               type=hot_type,
                                               csar_dir=csar_dir)
        self.policy = policy
        self.scaled_res = []

    def handle_expansion(self):
        hot_resources = []
        if self.policy.entity_tpl.get('triggers'):
            sample = self.policy.\
                entity_tpl["triggers"]["resize_compute"]["condition"]
            prop = {}
            prop["description"] = self.policy.entity_tpl.get('description')
            prop["meter_name"] = "cpu_util"
            if sample:
                prop["statistic"] = ALARM_STATISTIC[sample["method"]]
                prop["period"] = sample["period"]
                prop["threshold"] = sample["evaluations"]
            prop["comparison_operator"] = "gt"
            alarm_name = self.name.replace('_scale_in', '').\
                replace('_scale_out', '')
            ceilometer_resource = HotResource(self.nodetemplate,
                                              type='OS::Aodh::Alarm',
                                              name=alarm_name + '_alarm',
                                              properties=prop)
            hot_resources.append(ceilometer_resource)

        # remove the scaled res for now,
        # we don't want to deepcopy it
        local_scaled_res = self.scaled_res
        self.scaled_res = []

        extra_res = copy.deepcopy(self)
        scaling_adjustment = self.properties['scaling_adjustment']
        if scaling_adjustment < 0:
            self.name += '_scale_in'
            extra_res.name += '_scale_out'
            extra_res.properties['scaling_adjustment'] = \
                -1 * scaling_adjustment
            hot_resources.append(extra_res)
        elif scaling_adjustment > 0:
            self.name += '_scale_out'
            extra_res.name += '_scale_in'
            extra_res.properties['scaling_adjustment'] = \
                -1 * scaling_adjustment
            hot_resources.append(extra_res)

        self.scaled_res = local_scaled_res

        return hot_resources

    def represent_ordereddict(self, dumper, data):
        nodes = []
        for key, value in data.items():
            node_key = dumper.represent_data(key)
            node_value = dumper.represent_data(value)
            nodes.append((node_key, node_value))
        return yaml.nodes.MappingNode(u'tag:yaml.org,2002:map', nodes)

    def _handle_nested_template(self, resources):
        template_dict = yaml.load(HEAT_TEMPLATE_BASE)
        template_dict["resources"] = {}

        asgs = []

        servers_to_scale = []
        for res in self.scaled_res:
            if res.type == "OS::Nova::Server":
                servers_to_scale.append(res)

        # create a substack to embed the server
        # and its dependencies
        template, parameters, deps = self.create_substack_from_servers(
            servers_to_scale, resources)

        substack_props = {'type': template}
        if parameters:
            substack_props['properties'] = parameters

        temp = self.policy.entity_tpl["properties"]
        asg_props = {}
        asg_props["min_size"] = temp["min_instances"]
        asg_props["max_size"] = temp["max_instances"]
        asg_props["desired_capacity"] = temp["default_instances"]
        if "cooldown" in temp:
            asg_props["cooldown"] = temp["cooldown"]
        asg_props['resource'] = substack_props
        asg = HotResource(None,
                          type='OS::Heat::AutoScalingGroup',
                          name=self.policy.name,
                          properties=asg_props)
        asg.depends_on = deps

        resources.append(asg)
        asgs.append(asg)

        self.scaled_res = asgs

    def handle_properties(self, resources):
        if self.type == "OS::Heat::AutoScalingGroup" or \
                self.type == 'OS::Senlin::Policy':
            return

        self.properties = {}
        self.properties["auto_scaling_group_id"] = {
            'get_resource': self.policy.name
        }
        self.properties["adjustment_type"] = "change_in_capacity "
        self.properties["scaling_adjustment"] = self.\
            policy.entity_tpl["properties"]["increment"]
        if "cooldown" in self.policy.entity_tpl["properties"]:
            self.properties["cooldown"] = \
                self.policy.entity_tpl["properties"]["cooldown"]

        for resource in resources:
            if resource.name in self.policy.targets and \
                    resource.type not in SCALING_RESOURCES:
                self.scaled_res.append(resource)

        self._handle_nested_template(resources)

    def extract_substack_templates(self, base_filename, hot_template_version):
        nested_templates = {}
        substacks_resources = []
        base_filename, ext = os.path.splitext(base_filename)
        for res in self.scaled_res:
            if res.type == 'OS::Heat::AutoScalingGroup':
                substack = res.properties['resource']['type']
                filename = base_filename + "_" + res.name + ext
                res.properties['resource']['type'] = filename
                substacks_resources.extend(substack.resources)
                nested_templates[filename] = \
                    substack.output_to_yaml(True, hot_template_version)

        return nested_templates, substacks_resources
