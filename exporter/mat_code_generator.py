

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
        if 'output_node_name' in tree:
            output_node = tree['nodes'][tree['output_node_name']]
            outs = self.get_outputs(output_node)

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
        # NOTE: This is Blender's varposition!
        return self.varying(dict(type='PROJ_POSITION', datatype='vec3'))

    def view_normal(self):
        return self.varying(dict(type='VIEW_NORMAL', datatype='vec3'))

    def orco(self):
        return self.varying(dict(type='ORCO', datatype='vec3'))

    def uv(self, name=''):
        return self.varying(dict(type='UV', datatype='vec2', attname=name))

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

    def default_tangent(self, var):
        # TODO: Make sure it needs the model view matrix and not the view matrix (and its inverse)
        return self.get_op_cache(['vec3'],
            "default_tangent({}, {}, {}, {}, {}, {{}});"\
                .format(self.facingnormal()(), var(), self.object_matrix()(), self.model_view_matrix()(), self.view_matrix_inverse()()))[0]

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

    ## Direct node functions ##

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

    def tex_coord(self, invars, props):
        generated, normal, uv, object, camera, window, reflection = self.node_tex_coord()
        return '', dict(Generated=generated, Normal=normal, Uv=uv, Object=object,
                        Camera=camera, Window=window, Reflection=reflection)

    def tex_image(self, invars, props):
        ## node_tex_image co input uses mapping() with an identity matrix for some reason
        ## at least with orco. If something's wrong see if mapping was necessary
        co = invars['Vector']
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

    def bsdf_diffuse(self, invars, props):
        color0 = invars['Color'].to_color4()
        roughness = invars['Roughness'].to_float()
        normal = invars['Normal'].to_vec3()

        N = self.normalize(self.view2world_v3(self.facingnormal()))
        T = self.normalize(self.view2world_v3(self.default_tangent(self.orco())))
        ior = self.value_to_var(0.0)
        sigma = self.value_to_var(0.0)
        toon_size = self.value_to_var(0.0)
        toon_smooth = self.value_to_var(0.0)
        anisotropy = self.value_to_var(0.0)
        aniso_rotation = self.value_to_var(0.0)
        ao_factor = self.ssao()
        env_sampling_out = self.tmp('vec3')
        total_light = self.value_to_var([0.0,0.0,0.0,0.0])

        for lamp in self.lamps:
            # TODO: We're skipping a few things here and there and ignoring light nodes
            # It should be enough for bsdf diffuse for now
            light, visifac = self.bsdf_diffuse_sphere_light(lamp)
            lamp_color = self.uniform(dict(lamp=lamp['name'], type='LAMP_COL', datatype='color4'))
            strength = self.uniform(dict(lamp=lamp['name'], type='LAMP_STRENGTH', datatype='float'))
            col_by_strength = self.shade_mul_value_v3(strength, lamp_color)
            light2 = self.shade_mul_value(visifac, col_by_strength)
            total_light = self.shade_madd_clamped(total_light, light, light2)

        self.code.append("env_sampling_diffuse(0.0, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {});".format(
            self.view_position()(), self.view_matrix_inverse()(), self.model_view_matrix()(),
            N(), T(), roughness, ior(), sigma(), toon_size(), toon_smooth(),
            anisotropy(), aniso_rotation(), ao_factor(), env_sampling_out()))

        ambient = self.shade_clamp_positive(env_sampling_out)
        return self.node_bsdf_opaque(color0, ambient(), total_light())

    def bsdf_glossy(self, invars, props):
        color0 = invars['Color'].to_color4()
        roughness = invars['Roughness'].to_float()
        normal = invars['Normal'].to_vec3()

        N = self.normalize(self.view2world_v3(self.facingnormal()))
        T = self.normalize(self.view2world_v3(self.default_tangent(self.orco())))
        ior = self.value_to_var(0.0)
        sigma = self.value_to_var(0.0)
        toon_size = self.value_to_var(0.0)
        toon_smooth = self.value_to_var(0.0)
        anisotropy = self.value_to_var(0.0)
        aniso_rotation = self.value_to_var(0.0)
        ao_factor = self.ssao()
        env_sampling_out = self.tmp('vec3')
        total_light = self.value_to_var([0.0,0.0,0.0,0.0])

        for lamp in self.lamps:
            # TODO: We're skipping a few things here and there and ignoring light nodes
            # It should be enough for bsdf glossy_ggx for now
            light, visifac = self.bsdf_glossy_ggx_sphere_light(lamp, roughness)
            lamp_color = self.uniform(dict(lamp=lamp['name'], type='LAMP_COL', datatype='color4'))
            strength = self.uniform(dict(lamp=lamp['name'], type='LAMP_STRENGTH', datatype='float'))
            col_by_strength = self.shade_mul_value_v3(strength, lamp_color)
            light2 = self.shade_mul_value(visifac, col_by_strength)
            total_light = self.shade_madd_clamped(total_light, light, light2)

        self.code.append("env_sampling_glossy_ggx(0.0, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {});".format(
            self.view_position()(), self.view_matrix_inverse()(), self.model_view_matrix()(),
            N(), T(), roughness, ior(), sigma(), toon_size(), toon_smooth(),
            anisotropy(), aniso_rotation(), ao_factor(), env_sampling_out()))

        ambient = self.shade_clamp_positive(env_sampling_out)
        return self.node_bsdf_opaque(color0, ambient(), total_light())

    def bsdf_toon(self, invars, props):
        color0 = invars['Color'].to_color4()
        normal = invars['Normal'].to_vec3()
        toon_size = invars['Size'].to_float()
        toon_smooth = invars['Smooth'].to_float()

        N = self.normalize(self.view2world_v3(self.facingnormal()))
        T = self.normalize(self.view2world_v3(self.default_tangent(self.orco())))
        roughness = self.value_to_var(0.0)
        ior = self.value_to_var(0.0)
        sigma = self.value_to_var(0.0)
        anisotropy = self.value_to_var(0.0)
        aniso_rotation = self.value_to_var(0.0)
        ao_factor = self.ssao()
        env_sampling_out = self.tmp('vec3')
        total_light = self.value_to_var([0.0,0.0,0.0,0.0])

        for lamp in self.lamps:
            # TODO: We're skipping a few things here and there and ignoring light nodes
            # It should be enough for bsdf glossy_ggx for now
            light, visifac = self.bsdf_toon_diffuse_sphere_light(lamp, toon_size, toon_smooth)
            lamp_color = self.uniform(dict(lamp=lamp['name'], type='LAMP_COL', datatype='color4'))
            strength = self.uniform(dict(lamp=lamp['name'], type='LAMP_STRENGTH', datatype='float'))
            col_by_strength = self.shade_mul_value_v3(strength, lamp_color)
            light2 = self.shade_mul_value(visifac, col_by_strength)
            total_light = self.shade_madd_clamped(total_light, light, light2)

        self.code.append("env_sampling_toon_diffuse(0.0, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {});".format(
            self.view_position()(), self.view_matrix_inverse()(), self.model_view_matrix()(),
            N(), T(), roughness(), ior(), sigma(), toon_size, toon_smooth,
            anisotropy(), aniso_rotation(), ao_factor(), env_sampling_out()))

        ambient = self.shade_clamp_positive(env_sampling_out)
        return self.node_bsdf_opaque(color0, ambient(), total_light())

    def mix_shader(self, invars, props):
        factor = invars['Fac'].to_float()
        shader0 = invars['Shader'].to_color4()
        shader1 = invars['Shader$2'].to_color4()
        out = self.tmp('color4')
        code = "node_mix_shader({}, {}, {}, {});".format(factor, shader0, shader1, out())
        return code, {'Shader': out}

    # Indirect BSDF* #
    def node_bsdf_opaque(self, color, ambient, direct):
        out = self.tmp('vec4')
        code = "node_bsdf_opaque({},{},{},{});".format(color, ambient, direct, out())
        outputs = dict(BSDF=out)
        return code, outputs

    # Lights #
    def bsdf_diffuse_sphere_light(self, lamp):
        lv, dist, visifac = self.lamp_visibility_other(lamp)
        N = self.viewN_to_shadeN(self.facingnormal())
        l_areasizex = self.uniform(dict(lamp=lamp['name'], type='LAMP_SIZE', datatype='float'))
        out = self.tmp('float')
        self.code.append(
	"bsdf_diffuse_sphere_light({}, vec3(0.0), {}, vec3(0.0), vec3(0.0), {}, {}, 0.0, vec2(1.0), mat4(0.0),0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {});".format
            (N(), lv(), dist(), l_areasizex(), out()))
        return out, visifac

    def bsdf_glossy_ggx_sphere_light(self, lamp, roughness):
        lv, dist, visifac = self.lamp_visibility_other(lamp)
        N = self.viewN_to_shadeN(self.facingnormal())
        l_areasizex = self.uniform(dict(lamp=lamp['name'], type='LAMP_SIZE', datatype='float'))
        out = self.tmp('float')
        self.code.append(
	"bsdf_glossy_ggx_sphere_light({}, vec3(0.0), {}, {}, vec3(0.0), {}, {}, 0.0, vec2(1.0), mat4(0.0), {}, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {});".format
            (N(), lv(), self.view_position()(), dist(), l_areasizex(),
             roughness, out()))
        return out, visifac

    def bsdf_toon_diffuse_sphere_light(self, lamp, toon_size, toon_smooth):
        lv, dist, visifac = self.lamp_visibility_other(lamp)
        N = self.viewN_to_shadeN(self.facingnormal())
        l_areasizex = self.uniform(dict(lamp=lamp['name'], type='LAMP_SIZE', datatype='float'))
        out = self.tmp('float')
        self.code.append(
	"bsdf_toon_diffuse_sphere_light({}, vec3(0.0), {}, {}, vec3(0.0), {}, {}, 0.0, vec2(1.0), mat4(0.0), 0.0, 0.0, 0.0, {}, {}, 0.0, 0.0, {});".format
            (N(), lv(), self.view_position()(), dist(), l_areasizex(),
             toon_size, toon_smooth, out()))
        return out, visifac

    def lamp_visibility_other(self, lamp):
        lampco = self.uniform(dict(lamp=lamp['name'], type='LAMP_CO', datatype='vec3'))
        lv = self.tmp('vec3')
        dist = self.tmp('float')
        visifac = self.tmp('float')
        self.code.append(
	"lamp_visibility_other({}, {}, {}, {}, {});".format
            (self.view_position()(), lampco(), lv(), dist(), visifac()))
        return lv, dist, visifac
