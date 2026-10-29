"""Study tree for the desktop workbench."""
import json
from opensim.application.studies import STUDIES
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QTreeWidget, QTreeWidgetItem


class StudyTreeMixin:
    def add_study_tree(self, root, project, state):
        project_id = project["id"]
        parameters = project["parameters"]
        def node(parent, title, view="geometry", study=None, action=None):
            item = QTreeWidgetItem([title])
            item.setData(0, Qt.ItemDataRole.UserRole, (project_id, view))
            item.setData(0, Qt.ItemDataRole.UserRole + 1, study)
            item.setData(0, Qt.ItemDataRole.UserRole + 2, action)
            parent.addChild(item)
            return item
        node(root, "Geometry (shared)")
        element = "C3D10" if parameters["element_order"] == 2 else "C3D4"
        node(root, "Mesh / " + element + " (shared)", "mesh")
        support = "Selected region" if parameters["support_region"] else "X-min"
        force = parameters["load_axis"].upper() + " · " + ("selected faces" if parameters["load_region"] else parameters["load_kind"])
        def independent_nodes(branch,study):
            for i,load in enumerate(parameters['load_cases']):
                value=f"{load.get('pressure_Pa',0):g} Pa" if load['kind']=='pressure' else str(tuple(load['components_N']))+' N'
                title=(load.get('name') or f'Load {i+1}')+' / '+value+(' (disabled)' if not load.get('enabled',True) else '')
                entry=node(branch,title,study=study,action=f'load:{i}')
                entry.setToolTip(0,'Independent '+load['kind']+'; region: '+json.dumps(load.get('region') or {'surface':load.get('surface','x-max')}))
        for study, definition in STUDIES.items():
            if study=='cfd':continue
            title=definition.title
            branch = node(root, title, study=study)
            node(branch, "Fixed temperature / " + ("Selected region" if parameters['thermal_fixed_region'] else "X-min") if study == 'thermal' else "Fixed support / " + support, study=study)
            if study == "static":
                if parameters['load_cases']:independent_nodes(branch,study)
                else:node(branch, "Force / " + force, study=study)
                solution = node(branch, "Solution / Displacement and stress", "results", study)
            elif study == "modal":
                node(branch, "Density and requested modes", study=study)
                solution = node(branch, "Solution / Natural frequencies", "modal", study)
            elif study == 'thermal':
                node(branch, "Thermal source / " + parameters['thermal_boundary_mode'], study=study)
                solution = node(branch, "Solution / Temperature and heat flux", "thermal", study)
            else:
                if parameters['load_cases']:independent_nodes(branch,study)
                else:node(branch, "Static force / " + force, study=study)
                node(branch, "Mesh refinement settings", study=study)
                solution = node(branch, "Convergence report", study=study, action="convergence-report")
            node(branch, "Result plots", study=study, action="plots")
            active = project_id == state["project_id"] and study == state["study"]
            branch.setExpanded(active)
            if active:
                self.tree.setCurrentItem(solution if state["view"] in {"results", "modal", "thermal"} else branch)
        branch=node(root,'Fluid Dynamics',study='cfd')
        node(branch,'Fluid domain / '+parameters['cfd_domain_mode'],study='cfd')
        node(branch,'Fluid properties and flow conditions',study='cfd')
        node(branch,'Inlet / outlet boundaries','mesh','cfd')
        node(branch,'Fluid mesh','mesh','cfd')
        node(branch,'Velocity / center slice','cfd_slice','cfd')
        node(branch,'Surface pressure','cfd','cfd')
        node(branch,'Convergence / export','cfd_report','cfd')
        branch.setExpanded(project_id==state['project_id'] and state['study']=='cfd')
        if project_id==state['project_id'] and state['study']=='cfd':
            self.tree.setCurrentItem(branch);self.tree.scrollToItem(branch,QTreeWidget.ScrollHint.PositionAtTop)

    def select_tree_item(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and item.data(0,Qt.ItemDataRole.UserRole+1)=='cfd':
            self.cfd_select(data[0]);self.workspace.show_project(*data);self.refresh();return
        if data:
            if data[0] != self.project_id:
                try:
                    self.save_before_project_change()
                except Exception as error:
                    QMessageBox.warning(self, "Project settings", str(error))
                    return
            study = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if study:
                self.workspace.select_study(data[0], study)
            self.workspace.show_project(*data)
            action = item.data(0, Qt.ItemDataRole.UserRole + 2)
            self.refresh()
            if action == "convergence-report":
                self.safe(self.show_convergence_report)
            elif action == "plots":
                self.safe(self.show_plots)
            elif isinstance(action,str) and action.startswith('load:'):
                self.safe(self.edit_loads)
                if hasattr(self,'loads_dialog'):self.loads_dialog.list.setCurrentRow(int(action.split(':')[1]))
