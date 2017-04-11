
from .mesh import *
from .material import *
from .phy_mesh import *
from . import image
from .color import *

from json import dumps, loads
from collections import defaultdict
import shutil
import tempfile
import os
import struct
from math import *

import re

tempdir  = tempfile.gettempdir()

progress = 0
def add_progress(x=1):
    global progress
    progress += x
    bpy.context.window_manager.progress_update(progress)

def reset_progress():
    global progress
    progress = 0

def search_scene_used_data(scene):

    used_data = {
        'objects': [],
        'materials': [],
        'material_use_tangent': {},
        # materials don't have layers, but we'll assume their presence in layers
        # to determine which "this layer only" lights to remove
        'material_layers': {},
        'textures': [],
        'images': [],
        'image_users': defaultdict(list),
        'image_is_normal_map': {},
        'meshes': [],
        'actions': [],
        'action_users': {}, # only one user (ob or material) of each, to get the channels
        'sounds': {},
        }

    #recursive search methods for each data type:
    def add_ob(ob, i=0):
        if ob not in used_data['objects']:
            is_in_layers = ob_in_layers(scene, ob)
            print('    '*i+'Ob:', ob.name if is_in_layers else '('+ob.name+' not exported)')

            if is_in_layers:
                used_data['objects'].append(ob)
                if ob.type == 'MESH':
                    add_mesh(ob.data, i+1)
                if 'alternative_meshes' in ob:
                    for m in ob['alternative_meshes']:
                        add_mesh(bpy.data.meshes[m], i+1)

                for s in ob.material_slots:
                    if hasattr(s,'material') and s.material:
                        add_material(s.material, ob.layers, i+1)

                add_animation_data(ob.animation_data, ob, i+1)
                if ob.type=='MESH' and ob.data and ob.data.shape_keys:
                    add_animation_data(ob.data.shape_keys.animation_data, ob, i+1)

        for ob in ob.children:
            add_ob(ob, i+1)

    def add_action(action, i=0):
        if not action in used_data['actions']:
            print('    '*i+'Act:', action.name)
            used_data['actions'].append(action)

    def add_material(m, layers, i=0):
        if not m.name in used_data['material_layers']:
            use_normal_maps = False
            used_data['materials'].append(m)
            used_data['material_layers'][m.name] = list(layers)
            print('    '*i+'Mat:', m.name)
            for s,enabled in zip(m.texture_slots, m.use_textures):
                if enabled and hasattr(s, 'texture') and s.texture:
                    use_normal_map = getattr(s.texture, 'use_normal_map', False)
                    add_texture(s.texture,i+1, use_normal_map)
                    use_normal_maps = use_normal_maps or use_normal_map
            add_animation_data(m.animation_data, m, i+1)
            if m.use_nodes and m.node_tree:
                use_normal_maps = search_in_node_tree(m.node_tree, layers, i-1) or use_normal_maps
                add_animation_data(m.node_tree.animation_data, m.node_tree, i+1)
            used_data['material_use_tangent'][m.name] = used_data['material_use_tangent'].get(m.name, False) or use_normal_maps
        mlayers = used_data['material_layers'][m.name]
        for i,l in enumerate(layers):
            mlayers[i] = l or mlayers[i]
        return used_data['material_use_tangent'].get(m.name, False)

    # NOTE: It assumes that there is no cyclic dependencies in node groups.
    def search_in_node_tree(tree, layers, i=0):
        use_normal_map = False
        for n in tree.nodes:
            if (n.bl_idname == 'ShaderNodeMaterial' or n.bl_idname == 'ShaderNodeExtendedMaterial') and n.material:
                use_normal_map = add_material(n.material, layers, i+1) or use_normal_map
            elif n.bl_idname == 'ShaderNodeTexture' and n.texture:
                use_normal_map = use_normal_map or getattr(n.texture, 'use_normal_map', False)
                add_texture(n.texture,i+1)
            elif n.bl_idname == 'ShaderNodeGroup':
                if n.node_tree:
                    search_in_node_tree(n.node_tree, layers, i+1)
        return use_normal_map

    def add_texture(t,i=0, is_normal=False):
        if not t in used_data['textures']:
            print('    '*i+'Tex:', t.name)
            used_data['textures'].append(t)
            if t.type == 'IMAGE' and t.image:
                add_image(t.image,i+1)
                used_data['image_users'][t.image.name].append(t)
                used_data['image_is_normal_map'][t.image.name] = is_normal

    def add_image(i,indent=0):
        if not i in used_data['images']:
            print('    '*indent+'Img:', i.name)
            used_data['images'].append(i)

    def add_mesh(m,i=0):
        if not m in used_data['meshes']:
            print('    '*i+'Mes:', m.name)
            used_data['meshes'].append(m)

    def add_seq_strip(strip):
        if strip.type=='SOUND':
            used_data['sounds'][strip.sound.name] = strip.sound.filepath

    def add_animation_data(animation_data, user, i=0):
        any_solo = False
        if animation_data and animation_data.nla_tracks:
            any_solo = any([track.is_solo for track in animation_data.nla_tracks])
            for track in animation_data.nla_tracks:
                if (any_solo and not track.is_solo) or track.mute:
                    # solo shot first
                    continue
                for strip in track.strips:
                    if strip.type == 'CLIP' and not strip.mute:
                        add_action(strip.action, i+1)
                        used_data['action_users'][strip.action.name] = user

        action = animation_data and animation_data.action
        if not any_solo and action and action.fcurves:
            add_action(action, i+1)
            used_data['action_users'][action.name] = user

    # Searching and storing stuff in use:
    print('\nSearching used data in the scene: ' + scene.name + '\n')

    for ob in scene.objects:
        if not ob.parent:
            add_ob(ob)

    sequences = (scene.sequence_editor and scene.sequence_editor.sequences_all) or []
    for s in sequences:
        add_seq_strip(s)

    print("\nObjects:", len(used_data['objects']), "Meshes:", \
        len(used_data['meshes']), "Materials:", len(used_data['materials']), \
        "Textures:", len(used_data['textures']), "Images:", len(used_data['images']), \
        "Actions:", len(used_data['actions']))

    print ('\n')

    return used_data

def scene_data_to_json(scn=None):
    scn = scn or bpy.context.scene
    world = scn.world or bpy.data.scenes['Scene'].world
    sequences = (scn.sequence_editor and scn.sequence_editor.sequences_all) or []
    scene_data = {
        'type':'SCENE',
        'name': scn.name,
        'gravity' : [0,0,-scn.game_settings.physics_gravity], #list(scn.gravity),
        'background_color' : linearrgb_to_srgb([0,0,0], world.horizon_color),
        'ambient_color': linearrgb_to_srgb([0,0,0], world.ambient_color),
        'debug_physics': scn.game_settings.show_physics_visualization,
        'active_camera': scn.camera.name if scn.camera else 'Camera',
        'stereo': scn.game_settings.stereo == 'STEREO',
        'stereo_eye_separation': scn.game_settings.stereo_eye_separation,
        'frame_start': scn.frame_start,
        'frame_end': scn.frame_end,
        'fps': scn.render.fps,
        'markers': sorted([{
            'name': m.name,
            'frame': m.frame,
            'camera': m.camera and m.camera.name or '',
        } for m in scn.timeline_markers], key=lambda m:m['frame']),
        'sequencer_strips':  sorted([{
            'frame_start': s.frame_start,
            'type': s.type,
            'sound': s.sound.name if s.type=='SOUND' else '',
        } for s in sequences], key=lambda m:m['frame_start']),
    }
    return scene_data

#ported from animations.py
def interpolate(t, p0, p1, p2, p3):
    t2 = t * t
    t3 = t2 * t

    c0 = p0
    c1 = -3.0 * p0 + 3.0 * p1
    c2 = 3.0 * p0 - 6.0 * p1 + 3.0 * p2
    c3 = -p0 + 3.0 * p1 - 3.0 * p2 + p3

    return c0 + t * c1 + t2 * c2 + t3 * c3

#ported from gameengine/curve.py
def calc_curve_nodes(curves, resolution):
    curve = {'curves':curves, 'resolution':resolution, 'calculated_curves':[]}
    indices = []
    vertices = []
    n = 0
    curve['origins'] = origins = []
    for c in curves:
        cn = 0
        c_indices = []
        c_vertices = []
        for i in range((int(len(c)/9))-1):
            i9 = i*9
            p0x = c[i9+3]
            p0y = c[i9+4]
            p0z = c[i9+5]
            p1x = c[i9+6]
            p1y = c[i9+7]
            p1z = c[i9+8]
            p2x = c[i9+9]
            p2y = c[i9+10]
            p2z = c[i9+11]
            p3x = c[i9+12]
            p3y = c[i9+13]
            p3z = c[i9+14]
            for j in range(resolution):
                x = interpolate(j/resolution, p0x, p1x, p2x, p3x)
                y = interpolate(j/resolution, p0y, p1y, p2y, p3y)
                z = interpolate(j/resolution, p0z, p1z, p2z, p3z)

                vertices.extend([x,y,z])
                indices.append(n)
                indices.append(n+1)

                #sub_curve vertices and indices
                c_vertices.extend([x,y,z])
                c_indices.append(cn)
                c_indices.append(cn+1)

                n += 1
                cn += 1


        c_vertices.extend([p3x, p3y, p3z])
        curve['calculated_curves'].append({'ia':c_indices, 'va':c_vertices})
        vertices.extend([p3x, p3y, p3z])
        n += 1
        va = curve['va'] = vertices
        ia = curve['ia'] = indices
        curve_index = 0
        calculated_nodes = []

    def get_dist(a, b):
        x = b[0] - a[0]
        y = b[1] - a[1]
        z = b[2] - a[2]
        return sqrt(x*x + y*y + z*z)

    def get_nodes(main_curve_index=0, precission=0.0001):
        main_curve = curve['calculated_curves'][main_curve_index]

        nodes = {}

        for i in range(int(len(main_curve['ia'])/2)):
            i2 = i*2
            main_p = main_curve['va'][main_curve['ia'][i2]*3: main_curve['ia'][i2]*3+3]
            ci = 0
            for cc in curve['calculated_curves']:
                if ci != main_curve_index:
                    for ii in range(int(len(cc['ia'])/2)):
                        ii2 = ii*2
                        p = cc['va'][cc['ia'][ii2]*3: cc['ia'][ii2]*3+3]
                        d = get_dist(main_p,p)
                        if d < precission:
                            if not i in nodes:
                                nodes[i]=[[ci,ii]]
                            else:
                                nodes[i].append([ci,ii])
                                #nodes[node_vertex_index] = [attached_curve_index, attached_vertex_index]
                ci += 1
        return nodes

    for cc in curve['calculated_curves']:
        calculated_nodes.append(get_nodes(curve_index))
        curve_index += 1

    return calculated_nodes

def ob_to_json(ob, scn, check_cache, used_data):
    add_progress()
    scn = scn or [scn for scn in bpy.data.scenes if ob.name in scn.objects][0]
    scn['game_tmp_path'] = get_scene_tmp_path(scn) # TODO: have a changed_scene function
    data = {}
    #print(ob.type,ob.name)
    obtype = ob.type

    if obtype=='MESH':
        generate_tangents = any([used_data['material_use_tangent'][m.material.name] for m in ob.material_slots if m.material])
        if check_cache:
            print('Checking cache: ',ob.name, scn.name)
        # TODO: QUIRK: when the scene name is changed, cache is not invalidated
        # but new file can't be found (should files be moved?)
        cache_was_invalidated = False
        def convert(o, sort):
            nonlocal cache_was_invalidated
            cached_file = o.data.get('cached_file', 'i_dont_exist').replace('\\','/').rsplit('/',1).pop()
            invalid_cache = (not os.path.isfile(scn['game_tmp_path'] + cached_file)\
                or o.data.get('exported_name') != o.data.name)\
                or 'export_data' not in o.data\
                or 'avg_poly_area' not in loads(o.data.get('export_data','{}'))
            if not check_cache or invalid_cache:
                    cache_was_invalidated = True
                    split_parts = 1
                    add_progress()
                    while not convert_mesh(o, scn, split_parts, sort, generate_tangents):
                        if split_parts > 10:
                            raise Exception("Mesh "+o.name+" is too big.")
                        split_parts += 1

            scn['exported_meshes'][o.data['hash']] = scn['game_tmp_path'] + o.data['cached_file']
            return get_data_with_materials(o)

        def get_data_with_materials(o):
            d = loads(o.data['export_data'])
            materials = []
            passes = []
            for i in o.data.get('material_indices', []):
                n = 'Material'
                pass_ = 0
                mat = o.material_slots[i:i+1]
                mat = mat and mat[0]
                if mat and mat.material:
                    n = mat.name
                    if mat.material.use_transparency and \
                        mat.material.transparency_method == 'RAYTRACE':
                            pass_ = 2
                    elif mat.material.use_transparency and \
                            mat.material.game_settings.alpha_blend != 'CLIP':
                        pass_ = 1
                materials.append(n)
                passes.append(pass_)
            d['materials'] = materials or []
            d['passes'] = passes or [0]
            return d

        print('\nExporting object', ob.name)
        data = convert(ob, sort=bool(ob.get('sort_mesh', True)))
        tris_count = loads(ob.data['export_data']).get('tris_count',0)
        # copying conditions in mesh.py
        # because of linked meshes
        modifiers_were_applied = ob.get('modifiers_were_applied',
            not ob.data.shape_keys and \
            not ob.particle_systems)

        if 'alternative_meshes' in ob:
            orig_mesh = ob.data
            data['active_mesh_index'] = ob['active_mesh_index']
            data['alternative_meshes'] = []
            for d in ob['alternative_meshes']:
                ob.data = bpy.data.meshes[d]
                ob.data['compress_bits'] = orig_mesh.get('compress_bits')
                ob.data['byte_shapes'] = orig_mesh.get('byte_shapes')
                ob.data['uv_short'] = orig_mesh.get('uv_short')
                data['alternative_meshes'].append(convert(ob, sort=False))
            ob.data = bpy.data.meshes[ob['alternative_meshes'][ob['active_mesh_index']]]
        elif modifiers_were_applied: # No LoD for alt meshes, meshes with keys, etc
            if cache_was_invalidated or 'lod_level_data' not in ob.data:
                # Contains:  (TODO: sorted?)
                #    [
                #        {factor: 0.20,
                #         hash: 'abcdef',
                #         offsets, uv_multiplier, shape_multiplier}, ...
                #    ]

                lod_level_data = []
                lod_exported_meshes = {}

                if 'phy_mesh' in data:
                    del data['phy_mesh']
                phy_lod = ob.get('phy_lod', None)

                # Support two formats of "lod_levels":
                # - If you put an integer (or string with a number) you'll
                #   generate as many decimated levels, each half of the previous one
                #   e.g. 3 generates 3 levels with these factors:
                #   [0.50, 0.25, 0.125]
                # - If you put a list of numbers in a string, it will generate
                #   levels with those factors
                #   e.g. "[0.2, 0.08]"
                # In both cases, the level of factor 1 is implicit.

                def export_lod_mesh (ob, factor=0):
                    name = ob.name
                    orig_data = ob.data
                    ob.data = lod_mesh = ob.data.copy()
                    scn.objects.active = ob
                    lod_data = None

                    if factor:
                        print('Exporting LoD mesh with factor:', factor)
                        bpy.ops.object.modifier_add(type='DECIMATE')
                        ob.modifiers[-1].ratio = factor
                        ob.modifiers[-1].use_collapse_triangulate = True

                    try:
                        if not convert_mesh(ob, scn, 1, True, generate_tangents):
                            raise Exception("Decimated LoD mesh of "+name+" is too big")

                        lod_exported_meshes[lod_mesh['hash']] = scn['game_tmp_path'] + lod_mesh['cached_file']
                        lod_data = get_data_with_materials(ob)

                        exported_factor = lod_data['tris_count']/tris_count
                        print('Exported LoD mesh with factor:', exported_factor)

                        # TODO!! This is confusing. Should we copy lod_data
                        # and then add factor outside?
                        lod_level_data.append({
                            'factor': exported_factor,
                            'hash': lod_data['hash'],
                            'offsets': lod_data['offsets'],
                            'uv_multiplier': lod_data['uv_multiplier'],
                            'shape_multiplier': lod_data['shape_multiplier'],
                            'avg_poly_area': lod_data.get('avg_poly_area', None),
                            'materials': lod_data['materials'],
                            'passes': lod_data['passes'],
                        })
                    finally:
                        if factor:
                            bpy.ops.object.modifier_remove(modifier=ob.modifiers[-1].name)
                        ob.data = orig_data

                    return [lod_mesh, lod_data]

                def export_phy_mesh (ob, factor=0):
                    orig_data = ob.data
                    ob.data = ob.data.copy()
                    scn.objects.active = ob

                    if factor:
                        print ('Exporting phy_mesh with factor:', factor)
                        bpy.ops.object.modifier_add(type='DECIMATE')
                        ob.modifiers[-1].ratio = factor
                        ob.modifiers[-1].use_collapse_triangulate = True

                    try:
                        phy_data = convert_phy_mesh(ob, scn)
                        if not phy_data:
                            raise Exception("Phy LoD mesh is too big")
                        orig_data['phy_data'] = dumps(phy_data)

                        exported_factor = phy_data['export_data']['tris_count']/tris_count
                        print('Exported phy mesh with factor:', exported_factor)

                    finally:
                        if factor:
                            bpy.ops.object.modifier_remove(modifier=ob.modifiers[-1].name)
                        ob.data = orig_data
                    return phy_data

                #Exporting lod, phy, embed from modifiers

                lod_modifiers = []
                phy_modifier = None
                embed_modifiers = []

                for m in ob.modifiers:
                    if m.type == 'DECIMATE':
                        name = re.sub('[^a-zA-Z]', '.', m.name)
                        name = name.split('.')
                        if 'lod' in name:
                            m.show_viewport = False
                            lod_modifiers.append(m)
                        if 'phy' in name:
                            phy_modifier = m
                        if 'embed' in name:
                            embed_modifiers.append(m)

                for m in lod_modifiers:
                    m.show_viewport = True
                    lod_mesh, lod_data = export_lod_mesh(ob)
                    if m == phy_modifier:
                        print("This LoD mesh will be used as phy_mesh")
                        ob.data['phy_data'] = dumps({
                            'export_data': lod_data,
                            'cached_file': lod_mesh['cached_file'],
                        })
                    if m in embed_modifiers:
                        scn['embed_mesh_hashes'][lod_data['hash']] = True
                        embed_modifiers.remove(m)
                    m.show_viewport = False

                if phy_modifier and not phy_modifier in lod_modifiers:
                    phy_modifier.show_viewport = True
                    phy_mesh_data = export_phy_mesh(ob)
                    if phy_modifier in embed_modifiers:
                        scn['embed_mesh_hashes'][phy_mesh_data['hash']] = True
                        embed_modifiers.remove(m)
                    phy_modifier.show_viewport = False

                if embed_modifiers:
                    print('TODO! Embed mesh modifier without being LoD or Phy')

                #Exporting lod phy from object properties
                lod_levels = loads(str(ob.get('lod_levels',0)))
                if not isinstance(lod_levels, (int, list)):
                    print('WARNING: Invalid lod_levels type. Using lod_levels = 0')
                    lod_levels = 0

                if not isinstance(lod_levels, list):
                    lod_levels = [1/pow(2,lod_level+1)
                        for lod_level in range(lod_levels)]

                if phy_lod and phy_lod not in lod_levels and not phy_modifier:
                    export_phy_mesh(ob, phy_lod)
                    print()

                for factor in lod_levels:
                    lod_mesh, lod_data = export_lod_mesh(ob, factor)
                    if factor == phy_lod and not phy_modifier:
                        print("This LoD mesh will be used as phy_mesh")
                        ob.data['phy_data'] = dumps({
                            'export_data': lod_data,
                            'cached_file': lod_mesh['cached_file'],
                        })
                    print()

                lod_level_data = sorted(lod_level_data, key=lambda e: e['factor'])

                # end for
                ob.data['lod_level_data'] = dumps(lod_level_data)
                ob.data['lod_exported_meshes'] = lod_exported_meshes

            # end cache invalidated
            data['lod_levels'] = loads(ob.data['lod_level_data'])
            for k,v in ob.data['lod_exported_meshes'].items():
                scn['exported_meshes'][k] = v
            if ob.data.get('phy_data', None):
                phy_data = loads(ob.data['phy_data'])
                data['phy_mesh'] = phy_data['export_data']
                scn['exported_meshes'][phy_data['export_data']['hash']] = scn['game_tmp_path'] + phy_data['cached_file']
        # end if no alt meshes and modifiers_were_applied

        if not 'zindex' in ob:
            ob['zindex'] = 1
        data['zindex'] = ob['zindex']

    elif obtype=='CURVE':
        curves = []
        for c in ob.data.splines:
            l = len(c.bezier_points)
            handles1 = [0.0]*l*3
            points = [0.0]*l*3
            handles2 = [0.0]*l*3
            c.bezier_points.foreach_get('handle_left', handles1)
            c.bezier_points.foreach_get('co', points)
            c.bezier_points.foreach_get('handle_right', handles2)
            curve = [0.0]*l*9
            for i in range(l):
                i3 = i*3
                i9 = i*9
                curve[i9] = handles1[i3]
                curve[i9+1] = handles1[i3+1]
                curve[i9+2] = handles1[i3+2]
                curve[i9+3] = points[i3]
                curve[i9+4] = points[i3+1]
                curve[i9+5] = points[i3+2]
                curve[i9+6] = handles2[i3]
                curve[i9+7] = handles2[i3+1]
                curve[i9+8] = handles2[i3+2]
            curves.append(curve)

        data = {'curves': curves, 'resolution': ob.data.resolution_u}
        if True:#getattr(ob, 'pre_calc', False):
            data['nodes'] = calc_curve_nodes(data['curves'],data['resolution'])

        #print(curves)
    elif obtype=='CAMERA':
        data = {
            'angle': ob.data.angle,
            'clip_end': ob.data.clip_end,
            'clip_start': ob.data.clip_start,
            'ortho_scale': ob.data.ortho_scale,
            'sensor_fit': ob.data.sensor_fit, # HORIZONTAL VERTICAL AUTO
            'cam_type': ob.data.type          # PERSP ORTHO
        }
    elif obtype=='LAMP':
        data = {
            'lamp_type': ob.data.type,
            'color': list(ob.data.color*ob.data.energy),
            'energy': 1, # TODO: move energy here for when all assets no longer use the old way
            'falloff_distance': ob.data.distance,
            'shadow': getattr(ob.data, 'use_shadow', False),
            'tex_size': getattr(ob.data, 'shadow_buffer_size', 512),
            'frustum_size': getattr(ob.data, 'shadow_frustum_size', 0),
            'clip_start': getattr(ob.data, 'shadow_buffer_clip_start', 0),
            'clip_end': getattr(ob.data, 'shadow_buffer_clip_end', 0),
        }
    elif obtype=='ARMATURE':
        bones = []
        bone_dict = {}
        ordered_deform_names = []
        depends = defaultdict(set)
        num_deform = 0
        for bone in ob.data.bones:
            pos = bone.head_local.copy()
            if bone.parent:
                pos = bone.parent.matrix_local.to_3x3().inverted() * (pos - bone.parent.head_local)
            rot = bone.matrix.to_quaternion()
            bdata = {
                'name': bone.name,
                'parent': (bone.parent.name if bone.parent else ""),
                'position': list(pos),
                'rotation': rot[1:]+rot[0:1],
                'deform_id': -1,
                'constraints': [],
                'blength': bone.length,
            }
            bone_dict[bone.name] = bdata
            if bone.use_deform:
                bdata['deform_id'] = num_deform
                ordered_deform_names.append(bone.name)
                num_deform += 1
            for c in bone.children:
                depends[c.name].add(bone.name)
            depends[bone.name]
        # Each constraint: [function_name, owner idx, target idx, args...]
        # TODO: assuming target is own armature
        for bone in ob.pose.bones:
            for c in bone.constraints:
                if c.type.startswith('COPY_') and c.subtarget:
                    axes = [int(c.use_x), int(c.use_y), int(c.use_z)]
                    if axes.count(1)==1 and c.type=='COPY_ROTATION':
                        con = [c.type.lower()+'_one_axis', bone.name, c.subtarget, axes]
                    else:
                        con = [c.type.lower(), bone.name, c.subtarget]
                    bone_dict[bone.name]['constraints'].append(con)

                    depends[bone.name].add(c.subtarget)
                elif c.type == 'STRETCH_TO' and c.subtarget:
                    bone_dict[bone.name]['constraints'].append(
                        [c.type.lower(), bone.name, c.subtarget, c.rest_length, c.bulge])
                    depends[bone.name].add(c.subtarget)
                elif c.type == 'IK' and c.subtarget:
                    cl = c.chain_count or 9999
                    bone_dict[bone.name]['constraints'].append(
                        [c.type.lower(), bone.name, c.subtarget, c.chain_count, c.iterations])
                    depends[bone.name].add(c.subtarget)

        final_order = []
        last = set()
        while depends:
            next = set()
            for k,v in list(depends.items()):
                v.difference_update(last)
                if not v:
                    final_order.append(k)
                    next.add(k)
                    del depends[k]
            last = next
            if not next:
                print("ERROR: cyclic dependencies in", ob.name, "\n      ", ' '.join(depends.keys()))
                # TODO: find bones with less dependencies and no parent dependencies
                break
        bones = [bone_dict[name] for name in final_order]
        ob.data['ordered_deform_names'] = ordered_deform_names
        data = {'bones': bones, 'unfc': num_deform * 4}
        changed = False
        str_data = str(data)
        if ob.data.get('str_data') != str_data:
            changed = True
            ob.data['str_data'] = str_data

        pose = {}
        for bone in ob.pose.bones:
            pose[bone.name] = {
                'position': list(bone.location) if not ob.data.bones[bone.name].use_connect else [0,0,0],
                'rotation': bone.rotation_quaternion[1:]+bone.rotation_quaternion[0:1],
                'scale': list(bone.scale),
            }
        if changed or check_cache:
            data['pose'] = pose
            # Invalidate all children mesh caches
            for c in ob.children:
                if 'exported_name' in c:
                    del c['exported_name']
        else:
            # Send pose only
            data = {'pose': pose}
    else:
        obtype = 'EMPTY'

    if 'particles' in ob:
        data['particles'] = []
        for p in ob['particles']:
            particle = {}
            for k,v in p.items():
                if k == 'formula':
                    v = bpy.data.texts[v].as_string()
                particle[k] = v
            data['particles'].append(particle)
    rot_mode = ob.rotation_mode
    if rot_mode=='QUATERNION':
        rot = ob.rotation_quaternion
        rot_mode = 'Q'
    elif rot_mode == 'AXIS_ANGLE':
        print("WARNING: Axis angle not supported yet, converting to quat. Ob: "+ob.name)
        a,x,y,z = list(ob.rotation_axis_angle)
        sin2 = sin(a/2)
        rot = [cos(a/2), x*sin2, y*sin2, z*sin2]
        rot_mode = 'Q'
    elif scn.myou_export_convert_to_quats:
        rot = ob.rotation_euler.to_quaternion()
        rot_mode = 'Q'
    else:
        rot = [0] + list(ob.rotation_euler)

    # used for physics properties
    first_mat = ob.material_slots and ob.material_slots[0].material

    game_properties = {}
    for k,v in ob.items():
        if k not in ['modifiers_were_applied', 'zindex', 'cycles', 'cycles_visibility', '_RNA_UI']:
            if hasattr(v, 'to_list'):
                v = v.to_list()
            elif hasattr(v, 'to_dict'):
                v = v.to_dict()
            game_properties[k] = v
    for k,v in ob.game.properties.items():
        game_properties[k] = v.value

    parent = ob.parent.name if ob.parent else None
    if parent and ob.parent.proxy:
        parent = ob.parent.proxy.name

    strips = get_animation_data_strips(ob.animation_data)[0]
    if ob.type=='MESH' and ob.data and ob.data.shape_keys:
        strips += get_animation_data_strips(ob.data.shape_keys.animation_data)[0]

    obj = {
        'scene': scn.name,
        'type': obtype,
        'name': ob.name,
        'pos': list(ob.matrix_local.translation), # legacy (TODO remove when no longer used)
        'position': list(ob.location),
        'rot': list(rot),
        'rot_mode': rot_mode,
        'properties': game_properties,
        'scale': list(ob.scale),
        'offset_scale': [1,1,1],
        'matrix_parent_inverse': sum(list(map(list, ob.matrix_parent_inverse.transposed())),[]),
        'dimensions': list(ob.dimensions),
        'color' : list(ob.color),
        'parent': parent,
        'parent_bone': ob.parent_bone if parent and ob.parent.type == 'ARMATURE' and ob.parent_type == 'BONE' else '',
        'actions': [], # DEPRECATED
        'animation_strips': strips,
        'dupli_group': ob.dupli_group.name
            if ob.dupli_type=='GROUP' and ob.dupli_group else None,

        # Physics
        'phy_type': ob.game.physics_type,
        'visible': not ob.hide_render,
        'radius': ob.game.radius,
        'anisotropic_friction': ob.game.use_anisotropic_friction,
        'friction_coefficients': list(ob.game.friction_coefficients),
        'collision_group': sum([x*1<<i for i,x in enumerate(ob.game.collision_group)]),
        'collision_mask': sum([x*1<<i for i,x in enumerate(ob.game.collision_mask)]),
        'collision_bounds_type': ob.game.collision_bounds_type,
        'collision_margin': ob.game.collision_margin,
        'collision_compound': ob.game.use_collision_compound,
        'mass': ob.game.mass,
        'no_sleeping': ob.game.use_sleep,
        'is_ghost': ob.game.use_ghost,
        'linear_factor': [1 - int(ob.game.lock_location_x), 1 - int(ob.game.lock_location_y), 1 - int(ob.game.lock_location_z)],
        'angular_factor': [1 - int(ob.game.lock_rotation_x), 1 - int(ob.game.lock_rotation_y), 1 - int(ob.game.lock_rotation_z)],
        'form_factor': ob.game.form_factor,
        'friction': first_mat.physics.friction if first_mat else 0.5,
        'elasticity': first_mat.physics.elasticity if first_mat else 0,
    }
    if ob.game.physics_type == 'CHARACTER':
        obj.update({
            'step_height': ob.game.step_height,
            'jump_force': ob.game.jump_speed,
            'max_fall_speed': ob.game.fall_speed
        })
    obj.update(data)
    return obj

def get_animation_data_strips(animation_data): # TODO add prefix?
    if not animation_data:
        return [[],[]]
    strips = []
    any_solo = False
    if animation_data.nla_tracks:
        any_solo = any([track.is_solo for track in animation_data.nla_tracks])
        for track in animation_data.nla_tracks:
            if (any_solo and not track.is_solo) or track.mute:
                # solo shot first
                continue
            for strip in track.strips:
                if strip.type == 'CLIP' and not strip.mute and strip.action:
                    # Strips are added in the correct order of evaluation
                    # (tracks are from bottom to top)
                    strips.append({
                        'type': 'CLIP',
                        'extrapolation': strip.extrapolation,
                        'blend_type': strip.blend_type,
                        'frame_start': strip.frame_start,
                        'frame_end': strip.frame_end,
                        'blend_in': strip.blend_in,
                        'blend_out': strip.blend_out,
                        'reversed': strip.use_reverse,
                        'action': strip.action.name,
                        'action_frame_start': strip.action_frame_start,
                        'action_frame_end': strip.action_frame_end,
                        'scale': strip.scale,
                        'repeat': strip.repeat,
                        'name': strip.name or strip.action.name,
                    })
    action = animation_data.action
    if action and action.fcurves:
        strips.append({
            'type': 'CLIP',
            'extrapolation': 'HOLD',
            'blend_type': 'REPLACE',
            'frame_start': action.frame_range[0],
            'frame_end': action.frame_range[1],
            'blend_in': 0,
            'blend_out': 0,
            'reversed': False,
            'action': action.name,
            'action_frame_start': action.frame_range[0],
            'action_frame_end': action.frame_range[1],
            'scale': 1,
            'repeat': 1,
        })
    drivers = []
    last_path = ''
    if animation_data.drivers:
        for driver in animation_data.drivers:
            if last_path != driver.data_path:
                last_path = driver.data_path
                drivers.append(driver.data_path)
    return [strips, drivers]


def action_to_json(action, ob):
    # ob is any object or material which uses this, to check for use_connect
    # TYPE, NAME, CHANNEL, list of keys for each element
    # 'object', '', 'location', [[x keys], [y keys], [z keys]]
    # 'pose', bone_name, 'location', [...]
    # 'shape', shape_name, '', [[keys]]
    # Format for each channel element: [flat list of point coords]
    # each point is 6 floats that represent:
    # left handle, point, right handle

    channels = {} # each key is the tuple (type, name, channel)

    CHANNEL_SIZES = {'position': 3,
                     'rotation': 4, # quats with W
                     'rotation_euler': 3,
                     'scale': 3,
                     'color': 4}
    for fcurve in action.fcurves:
        path = fcurve.data_path.rsplit('.',1)
        chan = path[-1].replace('location', 'position')\
                       .replace('rotation_quaternion', 'rotation')
        name = ''
        chan_size = 1
        if len(path) == 1:
            type = 'object'
        else:
            if path[0].startswith('pose.'):
                type, name, _ = path[0].split('"')
                type = 'pose'

                if not hasattr(ob.data, 'bones') or not name in ob.data.bones:
                    # don't animate this channel (a bone that no longer exists was animated)
                    continue

                bone = ob.data.bones[name]
                if chan == 'position' and bone.parent and bone.use_connect:
                    # don't animate this channel, in blender it doesn't affect
                    # but in the engine it produces undesired results
                    continue

            elif path[0].startswith('key_blocks'):
                type = 'shape'
            elif ob.type in [
                    'SURFACE', 'WIRE', 'VOLUME', 'HALO', # Material
                    'SHADER']: # Material node tree
                type = 'material'
                chan = fcurve.data_path
                chan_size = 0
                for fcurve2 in action.fcurves:
                    if fcurve2.data_path == chan:
                        chan_size = max(fcurve2.array_index, chan_size)
                chan_size += 1
            else:
                print('Unknown fcurve path:', path[0], ob.type)
                continue
        k = type, name, chan
        if not k in channels:
            channels[k] = [[] for _ in range(CHANNEL_SIZES.get(chan, chan_size))]
        idx = fcurve.array_index
        if chan == 'rotation':
            idx = (idx - 1) % 4
        #print(k, fcurve.array_index)
        l = channels[k][idx]
        last_was_linear = False
        for k in fcurve.keyframe_points:
            p = [k.handle_left.x,
                 k.handle_left.y,
                 k.co.x, k.co.y,
                 k.handle_right.x,
                 k.handle_right.y]
            if last_was_linear:
                p[0] = p[2]
                p[1] = p[3]
                last_was_linear = False
            if k.interpolation == 'CONSTANT':
                p[4] = 1e200
                p[5] = p[3]
            elif k.interpolation == 'LINEAR':
                p[4] = p[2]
                p[5] = p[3]
                last_was_linear = True
            l.extend(p)

    final_action = {'type': 'ACTION',
                    'name': action.name,
                    'channels': [list(k)+[v] for (k,v) in channels.items()],
                    'markers': sorted([{
                        'name': m.name,
                        'frame': m.frame,
                        'camera': m.camera and m.camera.name or '',
                    } for m in action.pose_markers], key=lambda m:m['frame']),
    }

    return final_action


def ob_in_layers(scn, ob):
    return any(a and b for a,b in zip(scn.layers, ob.layers))


def ob_to_json_recursive(ob, scn, check_cache, used_data):
    d = [ob_to_json(ob, scn, check_cache, used_data)]
    for c in ob.children:
        if ob_in_layers(scn, c):
            d += ob_to_json_recursive(c, scn, check_cache, used_data)
    return d

def embed_meshes(scn):
    r = []
    for hash in scn['embed_mesh_hashes'].keys():
        mesh_bytes = open(scn['exported_meshes'][hash],'rb').read()
        if len(mesh_bytes)%4 != 0:
            mesh_bytes += bytes([0,0])
        int_list = struct.unpack('<'+str(int(len(mesh_bytes)/4))+'I', mesh_bytes)
        r.append({'type': 'EMBED_MESH', 'hash': hash, 'int_list': int_list})
    return r

def whole_scene_to_json(scn, used_data, textures_path):
    previous_scn = None
    if scn != bpy.context.screen.scene:
        # TODO: This never worked with materials
        # check if it works with the current version
        previous_scn = bpy.context.screen.scene
        bpy.context.screen.scene = scn

    # TODO: scene doesn't change back
    # Possible quirks of not changing scene:
    # * Meshes can't be exported
    # * Materials with custom uniforms can't be exported
    # Those are or may be cached to mitigate the issue

    was_editing = bpy.context.mode == 'EDIT_MESH'
    if was_editing:
        bpy.ops.object.editmode_toggle()
    # exported_meshes and embed_mesh_hashes will be filled
    # while exporting meshes from ob_to_json_recursive below
    scn['exported_meshes'] = {}
    scn['embed_mesh_hashes'] = {}
    scn['game_tmp_path'] = get_scene_tmp_path(scn) # TODO: have a changed_scene function

    # Start exporting scene settings, then the objects
    ret = [scene_data_to_json(scn)]
    for ob in used_data['objects']:
        if ob.parent:
            continue
        ret += ob_to_json_recursive(ob, scn, True, used_data)
    # This uses embed_mesh_hashes created above then filled in ob_to_json_recursive
    ret += embed_meshes(scn)
    # TODO: this is not currently used
    for group in bpy.data.groups:
        ret.append(
                {'type': 'GROUP',
                'name': group.name,
                'scene': scn.name,
                'offset': list(group.dupli_offset),
                'objects': [o.name for o in group.objects],
                })
    # Export shader lib, textures (images), materials, actions
    image_json = image.export_images(textures_path, used_data, add_progress)
    mat_json = [mat_to_json(mat, scn, used_data['material_layers'][mat.name])
                    for mat in used_data['materials']]
    act_json = [action_to_json(action, used_data['action_users'][action.name])
                    for action in used_data['actions']]
    # We must export shader lib after materials, but engine has to read it before
    ret.append({"type":"SHADER_LIB","code": get_shader_lib()})
    ret += image_json + mat_json + act_json
    # Final JSON encoding, without spaces
    retb = dumps(ret, separators=(',',':')).encode('utf8')
    retb_gz = gzip.compress(retb)
    size = len(retb)
    size_gz = len(retb_gz)
    # TODO empty scn['exported_meshes']?
    # for mesh_hash, fpath in scn['exported_meshes'].items():
    #     if mesh_hash not in scn['embed_mesh_hashes']:
    #         size += os.path.getsize(fpath)
    print('Total scene size: %.3f MiB (%.3f MiB compressed)' %
          (size/1048576, size_gz/1048576))
    scn['total_size'] = size
    if was_editing:
        bpy.ops.object.editmode_toggle()
    if previous_scn:
        bpy.context.screen.scene = previous_scn
    return [retb, retb_gz]


def get_scene_tmp_path(scn):
    dir = os.path.join(tempdir, 'scenes', scn.name + os.sep)
    for p in (os.path.join(tempdir, 'scenes'), dir):
        try:
            os.mkdir(p)
        except FileExistsError:
            pass
    return dir

import bpy
from bpy.props import StringProperty, BoolProperty
from bpy_extras.io_utils import ExportHelper

class MyouEngineExporter(bpy.types.Operator, ExportHelper):
    """Export scene as a HTML5 WebGL page."""
    bl_idname = "export_scene.myou"
    bl_label = "Export Myou"

    filename_ext = ".myou"
    filter_glob = StringProperty(default="*", options={'HIDDEN'})

    def execute(self, context):
        export_myou(self.filepath, context.scene)
        return {'FINISHED'}

def menu_export(self, context):
    self.layout.operator(MyouEngineExporter.bl_idname, text="Myou Engine")

def export_myou(path, scn):
    reset_progress()

    join = os.path.join

    if path.endswith('.myou'):
        path = path[:-5]
    data_dir = os.path.basename(path.rstrip('/').rstrip('\\').rstrip(os.sep))
    if data_dir:
        data_dir += os.sep
    full_dir = os.path.realpath(join(os.path.dirname(path), data_dir))
    old_export = ''
    if os.path.exists(full_dir):
        shutil.rmtree(full_dir, ignore_errors=False)
    try:
        os.mkdir(full_dir)
        os.mkdir(join(full_dir, 'scenes'))
        os.mkdir(join(full_dir, 'textures'))
        os.mkdir(join(full_dir, 'sounds'))
        for scene in bpy.data.scenes:
            used_data = search_scene_used_data(scene)
            textures_path = join(full_dir, 'textures')
            sounds_path = join(full_dir, 'sounds')
            scn_dir = join(full_dir, 'scenes', scene.name)
            try: os.mkdir(scn_dir)
            except FileExistsError: pass
            scene_json, scene_json_gz = whole_scene_to_json(scene, used_data, textures_path)
            open(join(scn_dir, 'all.json'), 'wb').write(scene_json)
            if scn.myou_export_compress_scene:
                open(join(scn_dir, 'all.json.gz'), 'wb').write(scene_json_gz)
            for mesh_file in scene['exported_meshes'].values():
                shutil.copy(mesh_file, scn_dir)
                if scn.myou_export_compress_scene:
                    shutil.copy(mesh_file+'.gz', scn_dir)
            for name,filepath in used_data['sounds'].items():
                apath = bpy.path.abspath(filepath)
                shutil.copy(apath, join(sounds_path, name))
            blend_dir = bpy.data.filepath.rsplit(os.sep, 1)[0]#.replace('\\','/')
            for fname in scene.myou_export_copy_files.split(' '):
                apath = join(blend_dir, fname)
                oname = fname.replace(os.sep, '/').replace('../','')
                print("exists",apath,os.path.isfile(apath))
                if fname and os.path.isfile(apath):
                    shutil.copy(apath, join(full_dir, oname))
    except:
        import datetime
        # shutil.move(full_dir, full_dir+'_FAILED_'+str(datetime.datetime.now()).replace(':','-').replace(' ','_').split('.')[0])
        # shutil.move(old_export, full_dir)
        # print("EXPORT HAS FAILED, but old folder has been restored")
        raise

    bpy.ops.file.make_paths_relative()
