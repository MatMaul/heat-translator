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

from collections import OrderedDict
import logging
import os
import textwrap
from toscaparser.utils.gettextutils import _
import yaml

log = logging.getLogger('heat-translator')


class HotTemplate(object):
    '''Container for full Heat Orchestration template.'''

    SECTIONS = (VERSION, DESCRIPTION, PARAMETER_GROUPS, PARAMETERS,
                RESOURCES, OUTPUTS, MAPPINGS) = \
               ('heat_template_version', 'description', 'parameter_groups',
                'parameters', 'resources', 'outputs', '__undefined__')

    VERSIONS = (LATEST,) = ('2013-05-23',)

    def __init__(self):
        self.resources = []
        self.outputs = []
        self.parameters = []
        self.description = ""

    def represent_ordereddict(self, dumper, data):
        nodes = []
        for key, value in data.items():
            node_key = dumper.represent_data(key)
            node_value = dumper.represent_data(value)
            nodes.append((node_key, node_value))
        return yaml.nodes.MappingNode(u'tag:yaml.org,2002:map', nodes)

    def get_hot_version(self):
        hot_template_version = self.LATEST
        for resource in self.resources:
            resource_version = resource.get_hot_version()
            if resource_version > hot_template_version:
                hot_template_version = resource_version
        return hot_template_version

    def output_to_yaml_files_dict(self, base_filename, hot_template_version=None):
        yaml_files_dict = {}

        if not hot_template_version:
            hot_template_version = self.get_hot_version()

        # convert from inlined substack to a substack defined in another file
        substacks = {}
        for resource in self.resources:
            substacks.update(resource.extract_substack_templates(base_filename,
                                                    hot_template_version))

        for substack_name in substacks:
            substack = substacks[substack_name]
            for resource in substack.resources:
                self.resources.remove(resource)

        yaml_files_dict[base_filename] = \
            self.output_to_yaml(False, hot_template_version)

        return yaml_files_dict

    def output_to_yaml(self, embed_substack_templates=True,
                       hot_template_version=None):
        log.debug(_('Converting translated output to yaml format.'))

        if not hot_template_version:
            hot_template_version = self.get_hot_version()

        dict_output = OrderedDict()
        # Version
        version_string = self.VERSION + ": " + hot_template_version + "\n\n"

        # Description
        desc_str = ""
        if self.description:
            # Wrap the text to a new line if the line exceeds 80 characters.
            wrapped_txt = "\n  ".join(textwrap.wrap(self.description, 80))
            desc_str = self.DESCRIPTION + ": >\n  " + wrapped_txt + "\n\n"

        # Parameters
        all_params = OrderedDict()
        for parameter in self.parameters:
            all_params.update(parameter.get_dict_output())
        dict_output.update({self.PARAMETERS: all_params})

        # Resources
        all_resources = OrderedDict()
        for resource in self.resources:
            if not resource.hide_resource:
                all_resources.update(resource.get_dict_output())
        dict_output.update({self.RESOURCES: all_resources})

        # Outputs
        all_outputs = OrderedDict()
        for output in self.outputs:
            all_outputs.update(output.get_dict_output())
        dict_output.update({self.OUTPUTS: all_outputs})

        yaml.add_representer(OrderedDict, self.represent_ordereddict)
        yaml.add_representer(dict, self.represent_ordereddict)
        yaml_string = yaml.dump(dict_output, default_flow_style=False)
        # get rid of the '' from yaml.dump around numbers
        # also replace double return lines with a single one
        # seems to be a bug in the serialization of multiline literal scalars
        yaml_string = yaml_string.replace('\'', '') .replace('\n\n', '\n')
        return version_string + desc_str + yaml_string
