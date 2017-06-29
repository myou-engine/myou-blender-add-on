

import json
from pprint import *
from collections import OrderedDict

# TODO:
# * Node groups
# * A lot of material nodes

class Variable:
    def __init__(self, name, type):
        self.name = name
        self.type = type
        self.used = False

    def __call__(self):
        self.used = True
        return self.name

    def glsl_type(self):
        return {'color3':'vec3','color4':'vec4'}.get(self.type, self.type)

    def to_float(self):
        if self.type=='float':
            return self()
        elif self.type in ['vec4','color4']:
            return "convert_rgba_to_float({})".format(self())
        elif self.type in ['color3']:
            return "convert_rgba_to_float({}.rgbb)".format(self())
        else:
            return self()+'.x'

    def to_vec3(self):
        if self.type=='float':
            return "vec3({})".format(self())
        elif self.type=='vec2':
            return "vec3({}.xy, 0.0)".format(self())
        elif self.type in ['vec3', 'color3']:
            return self()
        elif self.type in ['vec4','color4']:
            return self()+'.xyz'
        raise Exception(self.type)

    def to_color4(self):
        if self.type=='float':
            return "vec4(vec3({}), 1.0)".format(self())
        elif self.type=='vec2':
            return "vec4({}.xy, 0.0, 1.0)".format(self())
        elif self.type in ['vec3', 'color3']:
            return "vec4({}.xyz, 1.0)".format(self())
        elif self.type in ['vec4','color4']:
            return self()
        raise Exception(self.type)

    def to_normal(self, generator):
        if self.type in ['color3', 'color4']:
            tmp = generator.tmp('vec3')
            generator.code.append('')

class NodeTreeShaderGenerator:

    def __init__(self, tree, lamps):
        # Format of tree:
        # defined in mat_nodes.py
        # Format of lamps:
        # [{name: ob.name, lamp_type: ob.data.type}, ...]
        # TODO: Shadow configuration etc
        self.is_background = tree.get('is_background', False)
        self.node_cache = {}
        self.tree = tree
        self.lamps = lamps
        self.code = []
        self.tmp_index = 1
        self.tmp_vars = []
        self.op_cache = {}
        self.uniforms = OrderedDict()
        self.varyings = OrderedDict()
        print("EXPORTING MATERIAL",tree['material_name'])
        if 'output_node_name' in tree:
            output_node = tree['nodes'][tree['output_node_name']]
            outs = self.get_outputs(output_node)
        else:
            print('Warning: No output in material', tree['material_name'])

    def get_code(self):
        varyings = ['varying {} {};'.format(v.glsl_type(), v())
            for u,v in self.varyings.values()]
        # If it has varname already, it means it was already declared elsewhere
        uniforms = ['uniform {} {};'.format(v.glsl_type(), v())
            for u,v in self.uniforms.values() if 'varname' not in u]
        return '\n'.join(
            varyings+
            uniforms+
            ['void main(){']+
            ['    '+self.join_code(
                self.tmp_vars+
                self.code)]+
            ['}']
        )

    def get_uniforms(self):
        r = []
        for u,v in self.uniforms.values():
            d = u.copy()
            d['datatype'] = v.glsl_type()
            d['varname'] = v()
            r.append(d)
        return r

    def get_varyings(self):
        r = []
        for u,v in self.varyings.values():
            d = u.copy()
            d['datatype'] = v.glsl_type()
            d['varname'] = v()
            r.append(d)
        return r

    def join_code(self, code):
        indent = '    '
        return ('\n'+indent).join(code)

    def get_outputs(self, node):
        cached = self.node_cache.get(id(node), None)
        if cached:
            return cached
        invars = {}
        for name,input in node['inputs'].items():
            if 'value' in input:
                invars[name] = self.value_to_var(input['value'])
            elif 'link' in input:
                linked_node = self.tree['nodes'][input['link']['node']]
                invars[name] = self.get_outputs(linked_node)[input['link']['socket']]
            else:
                invars[name] = Variable('(0.0)', 'float')
        pprint(node['inputs'])
        if not hasattr(self, node['type'].lower()):
            pprint(node)
            raise Exception("Code for node {} not found".format(node['type']))
        code, outputs = getattr(self, node['type'].lower())(invars, node.get('properties'))
        self.code.append(code)
        self.node_cache[id(node)] = outputs
        return outputs

    def value_to_var(self, value):
        if isinstance(value, float):
            return Variable('('+str(value)+')', 'float')
        type = 'vec'+str(len(value))
        return Variable(type+'('+', '.join(map(str,value))+')', type)

    tmp_chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'

    def tmp(self, type):
        suffix = ''
        t = self.tmp_index
        suffix = self.tmp_chars[t%len(self.tmp_chars)]
        while t >= len(self.tmp_chars):
            t //= len(self.tmp_chars)
            suffix = self.tmp_chars[t%len(self.tmp_chars)] + suffix
        name = type+'_'+suffix
        v = Variable(name, type)
        self.tmp_vars.append(v.glsl_type()+' '+name+';')
        self.tmp_index += 1
        return v

    ## Varyings ##

    def varying(self, data):
        key = json.dumps(data, sort_keys=True)
        if key not in self.varyings:
            name = data['type'].lower() + str(len(self.varyings))
            self.varyings[key] = [data, Variable(name, data['datatype'])]
        return self.varyings[key][1]

    def view_position(self):
        return self.varying(dict(type='VIEW_POSITION', datatype='vec3'))

    def proj_position(self):
        return self.varying(dict(type='PROJ_POSITION', datatype='vec4'))

    def proj_position3(self):
        # NOTE: This is Blender's varposition! But it doesn't work.
        return Variable(self.varying(dict(type='PROJ_POSITION', datatype='vec4')).to_vec3(), 'vec3')

    def view_normal(self):
        return self.varying(dict(type='VIEW_NORMAL', datatype='vec3'))

    def orco(self):
        return self.varying(dict(type='ORCO', datatype='vec3'))

    def uv(self, name=''):
        return self.varying(dict(type='UV', datatype='vec2', attname=name))

    def attr_tangent(self, name=''):
        return self.varying(dict(type='TANGENT', datatype='vec4', attname=name))

    ## Uniforms ##

    def uniform(self, data):
        key = json.dumps(data, sort_keys=True)
        if key not in self.uniforms:
            name = data.get('varname', data['type'].lower() + str(len(self.uniforms)))
            self.uniforms[key] = [data, Variable(name, data['datatype'])]
        return self.uniforms[key][1]

    # Some of these are declared in shader_lib_extractor.py
    # so by assigning explicit varnames, they won't be added again
    def projection_matrix(self):
        return self.uniform(dict(type='PROJ_MAT', datatype='mat4',
                                 varname='projection_matrix'))

    def projection_matrix_inverse(self):
        return self.uniform(dict(type='PROJ_IMAT', datatype='mat4',
                                 varname='projection_matrix_inverse'))

    def model_view_matrix(self):
        return self.uniform(dict(type='OB_VIEW_MAT', datatype='mat4'))

    def view_matrix(self):
        return self.uniform(dict(type='VIEW_MAT', datatype='mat4'))

    def view_matrix_inverse(self):
        return self.uniform(dict(type='VIEW_IMAT', datatype='mat4'))

    def object_matrix(self):
        return self.uniform(dict(type='OB_MAT', datatype='mat4'))

    def object_matrix_inverse(self):
        return self.uniform(dict(type='OB_IMAT', datatype='mat4'))

    def rotation_matrix_inverse(self):
        return self.uniform(dict(type='VIEW_IMAT3', datatype='mat3',
                                 varname='view_imat3'))

    #def unfcameratexfactors(self):
        # TODO: also enable gl_ProjectionMatrix

    ## Indirect node functions (called by direct ones below) ##

    def get_op_cache(self, out_types, code):
        if code not in self.op_cache:
            outs = [self.tmp(out_type) for out_type in out_types]
            self.op_cache[code] = outs
            self.code.append(code.format(*(out.name for out in outs)))
        return self.op_cache[code]

    def facingnormal(self):
        return self.get_op_cache(['vec3'],
            "{{}} = gl_FrontFacing? {0}: -{0};".format(self.view_normal()()))[0]

    def shade_clamp_positive(self, var):
        return self.get_op_cache(['vec4'],
            "shade_clamp_positive({}, {{}});".format(var.to_color4()))[0]

    def ssao(self):
        return self.get_op_cache(['float'],
            "ssao({}, {}, {{}});".format(self.view_position()(), self.facingnormal()()))[0]

    def normalize(self, var):
        return self.get_op_cache([var.type],
            "vect_normalize({}, {{}});".format(var()))[0]

    def view2world_v3(self, var):
        # TODO: Make sure it needs the model view matrix and not the view matrix
        return self.get_op_cache([var.type],
            "direction_transform_m4v3({}, {}, {{}});".format(var(), self.view_matrix_inverse()()))[0]

    def world2view_v3(self, var):
        # TODO: Make sure it needs the model view matrix and not the view matrix
        return self.get_op_cache([var.type],
            "direction_transform_m4v3({}, {}, {{}});".format(var(), self.view_matrix()()))[0]

    def default_tangent(self):
        # This is the same as the "tangent" node with radial Z
        return self.get_op_cache(['vec3'],
            "default_tangent({}, {}, {}, {}, {}, {{}});"\
                .format(self.facingnormal()(), self.orco()(), self.object_matrix()(), self.view_matrix()(), self.view_matrix_inverse()()))[0]

    def viewN_to_shadeN(self, var):
        return self.get_op_cache([var.type],
            "viewN_to_shadeN({}, {{}});".format(var()))[0]

    def shade_mul_value_v3(self, a, b):
        return self.get_op_cache(['color3'],
            "shade_mul_value_v3({}, {}, {{}});".format(a.to_float(), b.to_vec3()))[0]

    def shade_mul_value(self, a, b):
        return self.get_op_cache(['color4'],
            "shade_mul_value({}, {}, {{}});".format(a.to_float(), b.to_color4()))[0]

    def shade_mul(self, a, b):
        return self.get_op_cache(['color4'],
            "shade_mul({}, {}, {{}});".format(a.to_color4(), b.to_color4()))[0]

    def shade_madd_clamped(self, a, b, c):
        return self.get_op_cache(['color4'],
            "shade_madd_clamped({}, {}, {}, {{}});"\
                .format(a.to_color4(), b.to_color4(), c.to_color4()))[0]

    def node_tex_coord(self):
        # TODO: Split into several individual functions triggered only when an output is used
        fname = "node_tex_coord"
        if self.is_background:
            fname += "_background"
            self.rotation_matrix_inverse()
        return self.get_op_cache(['vec3']*7,
            "{}({}, {}, {}, {}, {}, {}, {}, "\
                "{{}}, {{}}, {{}}, {{}}, {{}}, {{}}, {{}});"\
                .format(
                    fname,
                    self.view_position()(),
                    self.facingnormal()(),
                    self.view_matrix_inverse()(),
                    self.object_matrix_inverse()(),
                    'vec4(0.0)', #self.unfcameratexfactors()(),
                    self.orco()(),
                    self.uv().to_vec3()
                ))

    def background_transform_to_world(self):
        # even though this is already declared in the library,
        # we need to add it as uniform we're using
        self.rotation_matrix_inverse()
        # We're using the view position instead of proj position
        # (see shader_lib_extractor.py)
        return self.get_op_cache(['vec3'],
            "background_transform_to_world({}, {{}});"\
                .format(self.view_position()()))[0]

    def tangent_orco(self, axis):
        # axis is lowercase 'x', 'y', 'z'
        return self.get_op_cache(['vec3'],
            "tangent_orco_{}({}, {{}});"\
                .format(axis, self.orco()()))[0]

    ## Direct node functions ##

    ## Input nodes ##
    # TODO: we're mixing view_position and proj_position everywhere
    # but both are wrong, we need a corrected proj_position

    def camera(self, invars, props):
        outview = self.tmp('vec3')
        outdepth = self.tmp('float')
        outdist = self.tmp('float')
        code = "camera({}, {}, {}, {});".format(self.proj_position3()(), outview(), outdepth(), outdist())
        outputs = dict(View_Vector=outview, View_Z_Depth=outdepth, View_Distance=outdist)
        return code, outputs

    def fresnel(self, invars, props):
        ior = invars['IOR'].to_float()
        normal = invars['Normal'].to_vec3()
        if normal == 'vec3(0.0, 0.0, 0.0)': # if it's not connected
            normal = self.facingnormal()()
        out = self.tmp('float')
        code = "node_fresnel({}, {}, {}, {});".format(ior, normal, self.view_position()(), out())
        outputs = dict(Fac=out)
        return code, outputs

    def layer_weight(self, invars, props):
        blend = invars['Blend'].to_float()
        normal = invars['Normal'].to_vec3()
        if normal == 'vec3(0.0, 0.0, 0.0)': # if it's not connected
            normal = self.facingnormal()()
        fresnel = self.tmp('float')
        facing = self.tmp('float')
        code = "node_layer_weight({}, {}, {}, {}, {});".format(blend, normal, self.view_position()(), fresnel(), facing())
        outputs = dict(Fresnel=fresnel, Facing=facing)
        return code, outputs

    def new_geometry(self, invars, props):
        position = self.tmp('vec3')
        normal = self.tmp('vec3')
        tangent = self.tmp('vec3')
        true_normal = self.tmp('vec3')
        incoming = self.tmp('vec3')
        parametric = self.tmp('vec3')
        backfacing = self.tmp('float')
        pointiness = self.tmp('float')

        code = "node_geometry({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {});".format(
            self.view_position()(), self.facingnormal()(), self.orco()(),
            self.view_matrix_inverse()(), self.object_matrix()(),
            position(), normal(), tangent(), true_normal(), incoming(),
            parametric(), backfacing(), pointiness(),
        )
        outputs = dict(
            Position=position,
            Normal=normal,
            Tangent=tangent,
            True_Normal=true_normal,
            Incoming=incoming,
            Parametric=parametric,
            Backfacing=backfacing,
            Pointiness=pointiness,
        )
        return code, outputs

    def object_info(self, invars, props):
        location = self.tmp('vec3')
        obindex = self.tmp('float')
        matindex = self.tmp('float')
        random = self.tmp('float')
        code = "node_object_info({}, {}, {}, {}, {});".format(
            self.object_matrix()(), location(), obindex(), matindex(), random(),
        )
        outputs = dict(
            Location=location, Object_Index=obindex,
            Material_Index=matindex, Random=random,
        )
        return code, outputs

    def tangent(self, invars, props):
        tangent = self.tmp('vec3')
        ttype = props['direction_type']
        if ttype == 'RADIAL':
            if props['axis']=='Z':
                # optional optimization, since defailt_tangent() gives
                # the same value but may be cached
                code = ''
                tangent = self.default_tangent()
            else:
                v = self.tangent_orco(props['axis'].lower())
                code = "node_tangent({}, {}, {}, {}, {});".format(
                    self.facingnormal()(), v(),
                    self.object_matrix()(), self.view_matrix_inverse()(), tangent(),
                )
        elif ttype == 'UV_MAP':
            v = self.attr_tangent(props['uv_map'])
            code = "node_tangentmap({}, {}, {});".format(
                v(), self.view_matrix_inverse()(), tangent(),
            )
        else:
            raise Exception("Tangent type {} not implemented".format(ttype))
        outputs = dict(Tangent=tangent)
        return code, outputs

    def tex_coord(self, invars, props):
        # TODO: "window" output needs unfcameratexfactors
        generated, normal, uv, object, camera, window, reflection = self.node_tex_coord()
        return '', dict(Generated=generated, Normal=normal, UV=uv, Object=object,
                        Camera=camera, Window=window, Reflection=reflection)

    ## Output nodes ##

    def output_material(self, invars, props):
        in1 = invars['Surface'].to_color4()
        tmp = self.tmp('vec4')()
        code = ["linearrgb_to_srgb({0}, {1});"]
        if 0: # ALPHA_AS_DEPTH
            code += ["gl_FragColor = vec4({1}.rgb, {2}.z);"]
        else:
            code += ["gl_FragColor = {1};"]
        code = self.join_code(code).format(in1, tmp, self.view_position()())
        outputs = dict()
        return code, outputs

    def output_world(self, invars, props):
        in1 = invars['Surface'].to_color4()
        tmp = self.tmp('vec4')()
        code = ["linearrgb_to_srgb({0}, {1});"]
        code += ["gl_FragColor = {1};"]
        code = self.join_code(code).format(in1, tmp, self.view_position()())
        outputs = dict()
        return code, outputs

    math_ops = {
        'ADD': "{0} = {1}+{2};",
        'SUBTRACT': "{0} = {1}-{2};",
        'MULTIPLY': "{0} = {1}*{2};",
        'DIVIDE': "math_divide({1},{2},{0});",
        'SINE': "{0} = sin({1});",
        'COSINE': "{0} = cos({1});",
        'TANGENT': "{0} = tan({1});",
        'ARCSINE': "math_asin({1},{0});",
        'ARCCOSINE': "math_acos({1},{0});",
        'ARCTANGENT': "{0} = atan({1});",
        'POWER': "math_pow({1}, {2}, {0});",
        'LOGARITHM': "math_log({1}, {2}, {0});",
        'MINIMUM': "{0} = min({1}, {2});",
        'MAXIMUM': "{0} = max({1}, {2});",
        'ROUND': "{0} = floor({1}+0.5);",
        'LESS_THAN': "math_less_than({1},{2},{0});",
        'GREATER_THAN': "math_greater_than({1},{2},{0});",
        'MODULO': "math_modulo({1},{2},{0});",
        'ABSOLUTE': "{0} = abs({1});",
    }

    def math(self, invars, props):
        in1 = invars['Value'].to_float()
        in2 = invars['Value$1'].to_float()
        out = self.tmp('float')
        code = self.math_ops[props['operation']].format(out(), in1, in2)
        outputs = dict(Value=out)
        return code, outputs

    def combrgb(self, invars, props):
        r = invars['R'].to_float()
        g = invars['G'].to_float()
        b = invars['B'].to_float()
        out = self.tmp('color4')
        code = "combine_rgb({}, {}, {}, {});".format(r, g, b, out())
        outputs = dict(Image=out)
        return code, outputs

    def combxyz(self, invars, props):
        x = invars['X'].to_float()
        y = invars['Y'].to_float()
        z = invars['Z'].to_float()
        out = self.tmp('vec3')
        code = "combine_xyz({}, {}, {}, {});".format(x, y, z, out())
        outputs = dict(Vector=out)
        return code, outputs

    def sepxyz(self, invars, props):
        v = invars['Vector'].to_vec3();
        x = Variable("({}).x".format(v), 'float')
        y = Variable("({}).y".format(v), 'float')
        z = Variable("({}).z".format(v), 'float')
        return '', dict(X=x, Y=y, Z=z)

    BLEND_TYPES = {
        'MIX': 'blend',
        'ADD': 'add',
        'MULTIPLY': 'mult',
        'SUBTRACT': 'sub',
        'SCREEN': 'screen',
        'DIVIDE': 'div',
        'DIFFERENCE': 'diff',
        'DARKEN': 'dark',
        'LIGHTEN': 'light',
        'OVERLAY': 'overlay',
        'DODGE': 'dodge',
        'BURN': 'burn',
        'HUE': 'hue',
        'SATURATION': 'sat',
        'VALUE': 'val',
        'COLOR': 'color',
        'SOFT_LIGHT': 'soft',
        'LINEAR_LIGHT': 'linear',
    }

    def mix_rgb(self, invars, props):
        blend_type = self.BLEND_TYPES[props['blend_type']]
        fac = invars['Fac'].to_float()
        color1 = invars['Color1'].to_color4()
        color2 = invars['Color2'].to_color4()
        out = self.tmp('color4')
        code = "mix_{}({}, {}, {}, {});".format(blend_type, fac, color1, color2, out())
        outputs = dict(Color=out)
        if props['use_clamp']:
            clamped = self.tmp('vec3')
            self.code.append(code)
            code = "{} = clamp({}, vec3(0.0), vec3(1.0));".format(clamped(), out.to_vec3())
            outputs = dict(Color=clamped)
        return code, outputs

    def tex_image(self, invars, props):
        ## node_tex_image co input uses mapping() with an identity matrix for some reason
        ## at least with orco. If something's wrong see if mapping was necessary
        co = invars['Vector']
        if co() == 'vec3(0.0, 0.0, 0.0)': # if it's not connected
            co = self.uv()
        sampler = self.uniform(dict(type='IMAGE', datatype='sampler2D', image=props['image']))
        color = self.tmp('color4')
        alpha = self.tmp('float')
        self.code.append("node_tex_image({}, {}, {}, {});".format(
            co.to_vec3(), sampler(), color(), alpha()))
        if props['color_space'] == 'COLOR':
            out = self.tmp('color4')
            code = "srgb_to_linearrgb({},{});".format(color(), out())
        else:
            out = color
            out.type = 'vec4'
            code = ''
        return code, dict(Color=out, Alpha=alpha)

    def tex_environment(self, invars, props):
        ## node_tex_* co input use mapping() with an identity matrix for some reason
        ## at least with orco. If something's wrong see if mapping was necessary
        co = invars['Vector']
        if co() == 'vec3(0.0, 0.0, 0.0)': # if it's not connected
            co = self.background_transform_to_world()
        sampler = self.uniform(dict(type='IMAGE', datatype='sampler2D', image=props['image']))
        color = self.tmp('color4')
        if props['projection'] == 'EQUIRECTANGULAR':
            self.code.append("node_tex_environment_equirectangular({}, {}, {});".format(
                co.to_vec3(), sampler(), color()))
        elif props['projection'] == 'MIRROR_BALL':
            self.code.append("node_tex_environment_mirror_ball({}, {}, {});".format(
                co.to_vec3(), sampler(), color()))
        if props['color_space'] == 'COLOR':
            out = self.tmp('color4')
            code = "srgb_to_linearrgb({},{});".format(color(), out())
        else:
            out = color
            out.type = 'vec4'
            code = ''
        return code, dict(Color=out)

    def emission(self, invars, props):
        color = invars['Color'].to_color4()
        strength = invars['Strength'].to_float()
        out = self.tmp('color4')
        code = "node_emission({}, {}, vec3(0.0), {});".format(color, strength, out())
        return code, {'Emission': out}

    def background(self, invars, props):
        color = invars['Color'].to_color4()
        strength = invars['Strength'].to_float()
        out = self.tmp('color4')
        code = "node_background({}, {}, vec3(0.0), {});".format(color, strength, out())
        return code, {'Background': out}

    def bsdf_anisotropic(self, invars, props):
        color0 = invars['Color'].to_color4()
        normal = invars['Normal'].to_vec3()
        tangent = invars['Tangent'].to_vec3()
        return self.bsdf_opaque('anisotropic_'+props['distribution'].lower(),
            color0, normal, tangent,
            roughness=invars['Roughness'].to_float(),
            anisotropy=invars['Anisotropy'].to_float(),
            aniso_rotation=invars['Rotation'].to_float())

    def bsdf_diffuse(self, invars, props):
        color0 = invars['Color'].to_color4()
        normal = invars['Normal'].to_vec3()
        return self.bsdf_opaque('diffuse', color0, normal,
            roughness=invars['Roughness'].to_float())

    def bsdf_glass(self, invars, props):
        color0 = invars['Color'].to_color4()
        normal = invars['Normal'].to_vec3()
        return self.bsdf_opaque('glass_'+props['distribution'].lower(), color0, normal,
            roughness=invars['Roughness'].to_float(),
            ior=invars['IOR'].to_float())

    def bsdf_glossy(self, invars, props):
        color0 = invars['Color'].to_color4()
        normal = invars['Normal'].to_vec3()
        return self.bsdf_opaque('glossy_'+props['distribution'].lower(), color0, normal,
            roughness=invars['Roughness'].to_float())

    def bsdf_hair(self, invars, props):
        color0 = invars['Color'].to_color4()
        offset = invars['Offset'].to_float()
        roughnessU = invars['RoughnessU'].to_float()
        roughnessV = invars['RoughnessV'].to_float()
        tangent = invars['Tangent'].to_vec3()
        out = self.tmp('color4')
        code = "node_bsdf_hair({},{},{},{},{},{});".format(
            color0, offset, roughnessU, roughnessV, tangent, out())
        return code, dict(BSDF=out)

    def holdout(self, invars, props):
        return '', dict(Holdout=self.value_to_var([0.0,0.0,0.0,0.0]))

    def bsdf_refraction(self, invars, props):
        color0 = invars['Color'].to_color4()
        normal = invars['Normal'].to_vec3()
        return self.bsdf_opaque('refract_'+props['distribution'].lower(), color0, normal,
            roughness=invars['Roughness'].to_float(),
            ior=invars['IOR'].to_float())

    def bsdf_toon(self, invars, props):
        color0 = invars['Color'].to_color4()
        normal = invars['Normal'].to_vec3()
        return self.bsdf_opaque('toon_diffuse', color0, normal,
            toon_size=invars['Size'].to_float(),
            toon_smooth=invars['Smooth'].to_float())

    def bsdf_translucent(self, invars, props):
        color0 = invars['Color'].to_color4()
        normal = invars['Normal'].to_vec3()
        return self.bsdf_opaque('translucent', color0, normal)

    def bsdf_transparent(self, invars, props):
        # Not sure what's the point of this shader, but it works the same as in Blender PBR branch
        color0 = invars['Color'].to_color4()
        return self.bsdf_opaque('transparent', color0,
        # these are different than unconnected sockets, so they won't be calculated
        'vec3(0.0)', tangent='vec3(0.0)',
        use_lights=False)

    def subsurface_scattering(self, invars, props):
        color0 = invars['Color'].to_color4()
        scale = invars['Scale'].to_float()
        radius = invars['Radius'].to_vec3()
        sharpness = invars['Sharpness'].to_float()
        blur = invars['Texture_Blur'].to_float()
        normal = invars['Normal'].to_vec3()
        # out = self.tmp('color4')
        # code = "node_subsurface_scattering({},{},{},{},{},{},{});".format(
        #     color0, scale, radius, sharpness, blur, normal, out())
        out = self.value_to_var([0.0,0.0,0.0,0.0])
        code = ''
        return code, dict(BSSRDF=out)

    def bsdf_velvet(self, invars, props):
        color0 = invars['Color'].to_color4()
        normal = invars['Normal'].to_vec3()
        return self.bsdf_opaque('velvet', color0, normal,
            sigma=invars['Sigma'].to_float())

    def add_shader(self, invars, props):
        shader0 = invars['Shader'].to_color4()
        shader1 = invars['Shader$1'].to_color4()
        out = self.tmp('color4')
        code = "node_add_shader({}, {}, {});".format(shader0, shader1, out())
        return code, {'Shader': out}

    def mix_shader(self, invars, props):
        factor = invars['Fac'].to_float()
        shader0 = invars['Shader'].to_color4()
        shader1 = invars['Shader$2'].to_color4()
        out = self.tmp('color4')
        code = "node_mix_shader({}, {}, {}, {});".format(factor, shader0, shader1, out())
        return code, {'Shader': out}

    def ambient_occlusion(self, invars, props):
        color = invars['Color'].to_color4()
        out = self.tmp('color4')
        code = "node_bsdf_opaque({}, vec4(vec3({}), 1.0), vec4(0.0), {});".format(color, self.ssao()(), out())
        return code, {'AO': out}

    # Indirect BSDF* #
    def bsdf_opaque(self, bsdf_name, color, normal, tangent='vec3(0.0, 0.0, 0.0)',
            roughness='0.0', ior='0.0', sigma='0.0',
            toon_size='0.0', toon_smooth='0.0',
            anisotropy='0.0', aniso_rotation='0.0',
            use_lights=True):
        if normal == 'vec3(0.0, 0.0, 0.0)': # if it's not connected
            normal = self.normalize(self.view2world_v3(self.facingnormal()))()
        if tangent == 'vec3(0.0, 0.0, 0.0)': # if it's not connected or it has no socket
            view_tangent = self.normalize(self.default_tangent()) # optimize: remove normalize when not necessary
            tangent = self.normalize(self.view2world_v3(view_tangent))()
        else:
            view_tangent = self.world2view_v3(Variable(tangent, 'vec3'))
        ao_factor = self.ssao()
        env_sampling_out = self.tmp('vec3')
        total_light = self.value_to_var([0.0,0.0,0.0,0.0])

        for lamp in self.lamps:
            # TODO: We're ignoring light nodes
            if use_lights and lamp['use_diffuse']: # TODO: is use_specular used?
                light, visifac, shade_normal, lv = self.bsdf_lamp(bsdf_name, lamp, view_tangent(), roughness, toon_size, toon_smooth, anisotropy, aniso_rotation)
                # should we put this stuff inside bsdf_lamp?
                lamp_color = self.uniform(dict(lamp=lamp['name'], type='LAMP_COL', datatype='color4'))
                strength = self.uniform(dict(lamp=lamp['name'], type='LAMP_STRENGTH', datatype='float'))
                col_by_strength = self.shade_mul_value_v3(strength, lamp_color)
                light2 = self.shade_mul_value(visifac, col_by_strength)
                if lamp['lamp_type'] not in ['POINT', 'HEMI'] and lamp['use_shadow']:
                    if lamp['shadow_buffer_type'] == 'VARIANCE':
                        shadow = self.shadow_vsm(lamp['name'], shade_normal, lv)
                    else:
                        raise Exception("Unsupported shadow: "+lamp['shadow_buffer_type'])
                    light2 = self.shade_mul_value(shadow, light2)
                total_light = self.shade_madd_clamped(total_light, light, light2)

        bsdf_name = bsdf_name.replace('anisotropic_', 'aniso_')
        self.code.append("env_sampling_{}(0.0, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {});".format(
            bsdf_name, self.view_position()(), self.view_matrix_inverse()(), self.model_view_matrix()(),
            normal, tangent, roughness, ior, sigma, toon_size, toon_smooth,
            anisotropy, aniso_rotation, ao_factor(), env_sampling_out()))

        ambient = self.shade_clamp_positive(env_sampling_out)
        out = self.tmp('vec4')
        code = "node_bsdf_opaque({},{},{},{});".format(color, ambient(), total_light(), out())
        outputs = dict(BSDF=out)
        return code, outputs

    def bsdf_lamp(self, bsdf_name, lamp, view_tangent, roughness, toon_size, toon_smooth, anisotropy, aniso_rotation):
        lamp_type = lamp['lamp_type']
        if lamp_type == 'POINT':
            fname = 'sphere'
            lv, dist, visifac = self.lamp_visibility_other(lamp)
        elif lamp_type == 'SUN':
            fname = 'sun'
            lv = self.uniform(dict(lamp=lamp['name'], type='LAMP_DIR', datatype='vec3'))
            dist = self.value_to_var(1.0)
            visifac = self.value_to_var(100.0)
        else:
            raise Exception("Unknown lamp type "+lamp_type)
        l_areasizex = self.uniform(dict(lamp=lamp['name'], type='LAMP_SIZE', datatype='float'))

        N = self.viewN_to_shadeN(self.facingnormal())
        out = self.tmp('float')
        self.code.append(
    "bsdf_{}_{}_light({}, {}, {}, {}, vec3(0.0), {}, {}, 0.0, vec2(1.0), mat4(0.0), {}, 0.0, 0.0, {}, {}, {}, {}, {});".format
            (bsdf_name, fname, N(), view_tangent, lv(), self.view_position()(), dist(), l_areasizex(),
            roughness, toon_size, toon_smooth, anisotropy, aniso_rotation, out()))
            # missing: l_coords, l_areasizey, l_areascale, l_mat: only for area light
        return out, visifac, N, lv

    def lamp_visibility_other(self, lamp):
        lampco = self.uniform(dict(lamp=lamp['name'], type='LAMP_CO', datatype='vec3'))
        return self.get_op_cache(['vec3', 'float', 'float'],
            "lamp_visibility_other({}, {}, {{}}, {{}}, {{}});".format(self.view_position()(), lampco()))

    def shadow_vsm(self, lamp_name, shade_normal, lv):
        shade_inp = self.get_op_cache(['float'],
            "shade_inp({}, {}, {{}});".format(shade_normal(), lv()))[0]
        shadow_map = self.uniform(dict(lamp=lamp_name, type='LAMP_SHADOW_MAP', datatype='sampler2D'))
        shadow_proj = self.uniform(dict(lamp=lamp_name, type='LAMP_SHADOW_PROJ', datatype='mat4'))
        shadow_bias = self.uniform(dict(lamp=lamp_name, type='LAMP_SHADOW_BIAS', datatype='float'))
        bleed_bias = self.uniform(dict(lamp=lamp_name, type='LAMP_BLEED_BIAS', datatype='float'))
        return self.get_op_cache(['float'],
            "test_shadowbuf_vsm({}, {}, {}, {}, {}, {}, {{}});".format(
                self.view_position()(),
                shadow_map(),
                shadow_proj(),
                shadow_bias(),
                bleed_bias(),
                shade_inp(),
            ))[0]
