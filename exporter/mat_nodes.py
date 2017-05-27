 

import json
from pprint import *

# To be overwritten by set(dir(output_node)) if present
common_attributes = {'__doc__', '__module__', '__slots__', 'bl_description',
'bl_height_default', 'bl_height_max', 'bl_height_min', 'bl_icon', 'bl_idname',
'bl_label', 'bl_rna', 'bl_static_type', 'bl_width_default', 'bl_width_max',
'bl_width_min', 'color', 'dimensions', 'draw_buttons', 'draw_buttons_ext',
'height', 'hide', 'input_template', 'inputs', 'internal_links',
'is_active_output', 'is_registered_node_type', 'label', 'location', 'mute',
'name', 'output_template', 'outputs', 'parent', 'poll', 'poll_instance',
'rna_type', 'select', 'shading_compatibility', 'show_options', 'show_preview',
'show_texture', 'socket_value_update', 'type', 'update', 'use_custom_color',
'width', 'width_hidden'}

def unique_socket_name(socket):
    # If there's more than one socket with the same name,
    # each additional socket will have the index number
    sockets = socket.node.outputs if socket.is_output else socket.node.inputs
    idx = list(sockets).index(socket)
    name = socket.name.replace(' ','_')
    if sockets[name] != sockets[idx]:
        name += '$'+str(idx)
    return name

def export_node(node):
    out = {'type': node.type, 'inputs': {}}
    for input in node.inputs:
        inp = out['inputs'][unique_socket_name(input)] = {}
        socket_with_possible_value = input
        if input.links:
            socket_with_possible_value = None
            link = input.links[0]
            while link and link.is_valid and link.from_node.type == 'REROUTE':
                links = link.from_node.inputs[0].links
                link = links[0] if links else None
            if link and link.is_valid:
                inp['link'] = {
                    'node':link.from_node.name,
                    'socket':unique_socket_name(link.from_socket),
                }
                if link.from_node.type in ['VALUE','RGB']:
                    # This will make the input socket adopt the output of value/RGB nodes
                    socket_with_possible_value = link.from_socket
        if hasattr(socket_with_possible_value, 'default_value'):
            value = socket_with_possible_value.default_value
            if hasattr(value, '__iter__'):
                value = list(value)
            inp['value'] = value
            if 'link' in inp:
                del inp['link']
    properties = set(dir(node))-common_attributes
    if properties:
        out_props = out['properties'] = {}
    for prop in properties-{'node_tree'}:
        value = getattr(node, prop)
        value = getattr(value, 'name', value) # converts anything to its name
        if not isinstance(value, str) and hasattr(value, '__iter__'):
            value = list(value)
        ## If it's still not JSONable, convert it
        ## (not necessary yet since we're not exporting the tree for now)
        #if hasattr(value, 'bl_rna'):
            #converter_func = globals().get(value.__class__.__name__ + '2json')
            #if converter_func:
                #value = converter_func(value)
        out_props[prop] = value
        #print(' ', prop, repr(value))
    if node.type == 'GROUP':
        # we're embedding the group for now
        # (the better way is to have each group converted once)
        out['node_tree'] = export_nodes_of_group(node.node_tree)
    return out

def export_nodes_of_group(node_tree):
    # if there is more than one output, the good one is last
    output_node = None
    nodes = {}
    for node in node_tree.nodes:
        if node.type == 'GROUP_OUTPUT':
            output_node = node
    for node in node_tree.nodes:
        if node.type != 'REROUTE':
            nodes[node.name] = export_node(node)
    tree = {'nodes': nodes, 'output_node_name': output_node.name if output_node else ''}
    return tree

def export_nodes_of_material(mat): # NOTE: mat can also be a world
    global common_attributes
    # if there is more than one output, the good one is last
    output_node = None
    nodes = {}
    for node in mat.node_tree.nodes:
        if node.type in ['OUTPUT', 'OUTPUT_MATERIAL', 'OUTPUT_WORLD']:
            output_node = node
    if output_node:
        common_attributes = set(dir(output_node))
    for node in mat.node_tree.nodes:
        if node.type != 'REROUTE':
            nodes[node.name] = export_node(node)
    tree = {'nodes': nodes, 'output_node_name': output_node.name if output_node else ''}
    return tree

