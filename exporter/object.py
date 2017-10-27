
from .mesh import convert_mesh
from .phy_mesh import convert_phy_mesh
from .animation import get_animation_data_strips
from json import dumps, loads
from collections import defaultdict
import os
import re
from math import *
from . import progress

def ob_to_json(ob, scn, used_data, check_cache=True):
    progress.add()
    scn = scn or [scn for scn in bpy.data.scenes if ob.name in scn.objects][0]
    data = {}
    game_properties = {}

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
                    progress.add()
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

        if hasattr(ob, 'probe_type'):
            data['material_defines'] = material_defines = {}
            is_plane = ob.probe_type == 'PLANE'
            if not is_plane:
                # follow the probe chain to see if it's a plane
                real_probe_ob = ob
                while real_probe_ob and real_probe_ob.probe_type == 'OBJECT'\
                        and real_probe_ob.probe_object:
                    real_probe_ob = real_probe_ob.probe_object
                if real_probe_ob and real_probe_ob.probe_type == 'PLANE':
                    is_plane = True
            if is_plane:
                # by default defines without value have the value 0
                # but in this case it doesn't matter and 1 feels more correct than null
                material_defines['PLANAR_PROBE'] = 1

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
        size_x = size_y = 0
        if ob.data.type == 'AREA':
            size_x = ob.data.size
            size_y = ob.data.size if ob.data.shape == 'SQUARE' else ob.data.size_y
        elif ob.data.type != 'HEMI':
            size_x = size_y = ob.data.shadow_soft_size
        if scn.render.engine != 'CYCLES':
            color = list(ob.data.color*ob.data.energy)
            energy = 1 # we never modified this in the end
        elif ob.data.use_nodes and ob.data.node_tree and 'Emission' in ob.data.node_tree.nodes:
            # We'll use lamp nodes in the future
            # for now we'll just assume one emission node
            node = ob.data.node_tree.nodes['Emission']
            color = list(node.inputs['Color'].default_value)[:3]
            energy = node.inputs['Strength'].default_value * 0.01
        else:
            color = list(ob.data.color)
            energy = 1
            if ob.data.type == 'SUN':
                energy = 0.01
        data = {
            'lamp_type': ob.data.type,
            'color': color,
            'energy': energy,
            'falloff_distance': ob.data.distance,
            'shadow': getattr(ob.data, 'use_shadow', False),
            'shadow_bias': getattr(ob.data, 'shadow_buffer_bias', 0.001),
            'shadow_buffer_type': getattr(ob.data, 'ge_shadow_buffer_type', 'VARIANCE'),
            'bleed_bias': getattr(ob.data, 'shadow_buffer_bleed_bias', 0.1),
            'tex_size': getattr(ob.data, 'shadow_buffer_size', 512),
            'frustum_size': getattr(ob.data, 'shadow_frustum_size', 0),
            'clip_start': getattr(ob.data, 'shadow_buffer_clip_start', 0),
            'clip_end': getattr(ob.data, 'shadow_buffer_clip_end', 0),
            'size_x': size_x,
            'size_y': size_y,
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
        print("Deform bones:",num_deform,"uniforms",num_deform*4)
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
        data = {'mesh_radius': ob.empty_draw_size}
        game_properties = {
            '_empty_draw_type': ob.empty_draw_type,
            '_empty_draw_size': ob.empty_draw_size,
        }

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

    for k,v in ob.items():
        if k not in ['modifiers_were_applied', 'zindex', 'cycles', 'cycles_visibility', '_RNA_UI'] \
                and not isinstance(v, bytes):
            if hasattr(v, 'to_list'):
                v = v.to_list()
            elif hasattr(v, 'to_dict'):
                v = v.to_dict()
            game_properties[k] = v
    for k,v in ob.game.properties.items():
        game_properties[k] = v.value

    if getattr(ob, 'probe_type', 'NONE') != 'NONE':
        game_properties['probe_options'] = dict(
            type=ob.probe_type,
            object=getattr(ob.probe_object, 'name', ''),
            auto_refresh=ob.probe_refresh_auto,
            compute_sh=ob.probe_compute_sh,
            double_refresh=ob.probe_refresh_double,
            same_layers=ob.probe_use_layers,
            size=ob.probe_size,
            sh_quality=ob.probe_sh_quality,
            clip_start=ob.probe_clip_start,
            clip_end=ob.probe_clip_end,
            parallax_type=ob.probe_parallax_type,
            parallax_volume=getattr(ob.probe_parallax_volume, 'name', ''),
            # it may crash if we read this when not needed
            reflection_plane=getattr(ob.probe_reflection_plane, 'name', '') \
                if ob.probe_type=='PLANE' else '',
        )

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
        'offset_scale': [1,1,1], # TODO: no longer used, remove when sure
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

def ob_in_layers(scn, ob):
    return any(a and b for a,b in zip(scn.layers, ob.layers))


def ob_to_json_recursive(ob, scn, used_data):
    d = [ob_to_json(ob, scn, used_data)]
    for c in ob.children:
        if ob_in_layers(scn, c):
            d += ob_to_json_recursive(c, scn, used_data)
    return d
