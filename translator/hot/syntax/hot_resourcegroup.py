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

import os

from translator.hot.syntax.hot_resource import HotResource


class HotResourceGroup(HotResource):

    def __init__(self, nodetemplate, name, template, parameters, deps, nb, csar_dir=None):
        super(HotResourceGroup, self).__init__(nodetemplate,
                                               name=name,
                                               type='OS::Heat::ResourceGroup',
                                               depends_on=deps,
                                               csar_dir=csar_dir)

        substack_props = {'type': template}
        if parameters:
            substack_props['parameters'] = parameters

        self.properties = {'resource_def': substack_props, 'count': nb}

    def extract_substack_templates(self, base_filename, hot_template_version):
        nested_templates = {}
        base_filename, ext = os.path.splitext(base_filename)

        substack_template = self.properties['resource_def']['type']
        filename = base_filename + "_" + self.name + ext
        self.properties['resource_def']['type'] = filename
        nested_templates[filename] = substack_template

        return nested_templates

    def handle_properties(self, resources):
        pass
