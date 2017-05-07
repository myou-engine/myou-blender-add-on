bl_info = {
    "name": "Myou game engine",
    "author": "Alberto Torres Ruiz, Julio Manuel López Tercero",
    "version": (0, 5),
    "blender": (2, 69, 0),
    "location": "File > Export > Myou engine",
    "description": "Myou.cat game engine and Myou Logic Nodes compiler.",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Game Engine"}

# To find source of crashes (delete this when there are no crashes anymore)
import faulthandler
faulthandler.enable()

import bpy, sys, os, imp

from .exporter import exporter

auto_register_modules = [exporter]

from bpy.app.handlers import persistent



class ReloadMyouPlugin(bpy.types.Operator):
    bl_idname = "scene.myou_dev_reload"
    bl_label = "Reload Myou plugin"

    def execute(self, context):
        bpy.has_reloaded_myou = True
        unregister()
        reload_modules()
        module_name = os.path.realpath(__file__).rsplit(os.sep,2)[1]
        myou_bl_plugin = sys.modules[module_name]
        from imp import reload
        reload(myou_bl_plugin)
        myou_bl_plugin.register()
        return {'FINISHED'}

# -------------- LIST OF ALL REGISTERABLE CLASSES ----------

auto_register_classes = [
]

# Add the rest of the classes automatically
for m in auto_register_modules:
    ordered = []
    classes = []
    for c in m.__dict__.values():
        if hasattr(c, 'menu_order'):
            ordered.append(c)
        elif hasattr(c, 'bl_label'):
            classes.append(c)
    ordered.sort(key = lambda x:x.menu_order)
    classes.sort(key = lambda x: x.bl_label)
    auto_register_classes += ordered + classes

#------------- REGISTERING -------------

def try_unregister(c):
    try:
        bpy.utils.unregister_class(c)
    except RuntimeError:
        pass

def register():
    global updating
    for c in auto_register_classes:
        try_unregister(c)
        bpy.utils.register_class(c)
    try:
        bpy.utils.register_class(ReloadMyouPlugin)
    except:
        pass
    bpy.types.INFO_MT_file_export.append(exporter.menu_export)
    from . import export_panel
    export_panel.register()
    updating = False


def reload_modules():
    from .exporter import mesh, phy_mesh, image, material, color, shader_lib_extractor, \
        mat_nodes, mat_code_generator, mat_binternal
    from . import export_panel, winutils
    # For reloading changes in all modules when developing
    for m in [mesh, phy_mesh, image, shader_lib_extractor, mat_nodes, mat_code_generator, \
            mat_binternal, material, color, exporter, winutils, export_panel] + \
            auto_register_modules:
        imp.reload(m)


def unregister():
    from . import export_panel
    export_panel.unregister()
    bpy.types.INFO_MT_file_export.remove(exporter.menu_export)
    for c in reversed(auto_register_classes):
        try_unregister(c)
