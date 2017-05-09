from pprint import *
import re

replacements = [
    ('''/* These are needed for high quality bump mapping */
#version 130
#extension GL_ARB_texture_query_lod: enable
#define BUMP_BICUBIC''',''),
    # old shaders
    ('gl_ModelViewMatrixInverse','mat4(1)'),
    ('gl_ModelViewMatrix','mat4(1)'),
    ('gl_ProjectionMatrixInverse','mat4(1)'),
    ('gl_ProjectionMatrix[3][3]','0.0'),
    ('gl_ProjectionMatrix','mat4(1)'),
    ('gl_NormalMatrixInverse','mat3(1)'),
    ('gl_NormalMatrix','mat3(1)'),
    ('shadow2DProj(shadowmap, co).x',
            'step(co.z,texture2D(shadowmap, co.xy).x)'),
    ('gl_LightSource[i].position','vec3(0,0,0)'),
    ('gl_LightSource[i].diffuse','vec3(0,0,0)'),
    ('gl_LightSource[i].specular','vec3(0,0,0)'),
    ('gl_LightSource[i].halfVector','vec3(0,0,0)'),
    ('float rad[4], fac;', 'float rad[4];float fac;'),

    # newer shaders (2.78)
    ('(normalize(vec).z + 1)', '(normalize(vec).z + 1.0)'),
    ('strength * v1 + (1 - strength) * v2', 'strength * v1 + (1.0 - strength) * v2'),
    ('int(x) - ((x < 0) ? 1 : 0)', 'int(x) - ((x < 0.0) ? 1 : 0)'),
    ('return x - i;', 'return x - float(i);'),
    ('(M_PI * 2)', '(M_PI * 2.0)'),
    ('((mod(xi, 2) == mod(yi, 2)) == bool(mod(zi, 2)))', 'true'),
    (re.compile(r'if \(depth > (\d)\) {'), r'if (depth > \1.0) {'),
    ('fac = 1;', 'fac = 1.0;'),
    ('outv = -v;','outv = vec3(0.0)-v;'),

    # PBR branch
    ('#extension GL_EXT_gpu_shader4: enable', ''),
    ('sampler1D', 'sampler2D'),
    # TODO: 3rd argument is bias and not lod, and should use the extension where available
    ('texture2DLod', 'texture2DLodEXT'),
    ('textureCubeLod', 'textureCubeLodEXT'),
    (   'texture1DLod(unflutsamples, (float(u) + 0.5) / float(BSDF_SAMPLES), 0.0).rg;',
     'texture2DLodEXT(unflutsamples, vec2((float(u) + 0.5) / float(BSDF_SAMPLES), 0.5), 0.0).rg;'),
    (re.compile(r'(#define BSDF_SAMPLES \d+)'),r'\1.0'),
    (re.compile(r'(#define LTC_LUT_SIZE \d+)'),r'\1.0'),
    ('int NOISE_SIZE = 64;','float NOISE_SIZE = 64.0;'),
    ('	Xi.yz = texelFetch(unflutsamples, u, 0).rg;\n'*2,''), # This one is triplicated
    ('< 0)','< 0.0)'),
    ('>0)','>0.0)'),
    (' 2 *',' 2.0 *'),
    (' 4 *',' 4.0 *'),
    ('(1 +','(1.0 +'),
    ('(1 -','(1.0 -'),
    ('(1 *','(1.0 *'),
    ('(1 /','(1.0 /'),
    (' 1 / ',' 1.0 / '),
    ('- 1)','- 1.0)'),
    ('1.0f','1.0'),
    (', 2)',', 2.0)'), # pow
    ('/2,','/2.0,'),
    (' 1 -',' 1.0 -'),
    (' 2*',' 2.0*'),
    (' 3*',' 3.0*'),
    (' 8*',' 8.0*'),
    ('+ 4 ','+ 4.0 '),
    ('Y = 1;','Y = 1.0;'),
    ('ii -= i;','ii -= float(i);'),
    ('= 0)','= 0.0)'), # with exceptions below
    ('(config == 0.0)','(config == 0)'),
    ('(gradient_type == 0.0)','(gradient_type == 0)'),
    ('(n == 0.0)','(n == 0)'),
    ('float i = 0;','float i = 0.0;'),
    # we'll assign the uniform on run time
    (re.compile(r'(uniform vec3 node_wavelength_LUT\[81\]).*?\);', flags=re.DOTALL),r'\1;'),
    ('transpose(mat3(T1, T2, N))','mat3(T1.x, T2.x, N.x, T1.y, T2.y, N.y, T1.z, T2.z, N.z)'),

    # Cannot do dynamic loops
    ('uniform vec2 unfbsdfsamples;', ''),
    ('unfbsdfsamples.x', 32.0),
    ('unfbsdfsamples.y', 1/32.0),

]

argument_replacements = [
    ('sampler2DShadow','sampler2D'),
]

# Make sure \r are removed before calling this
def do_lib_replacements(lib):
    function_parts = re.compile(r"\n(\w+)\s+(\w+)\s*\((.*?)\)", flags=re.DOTALL).split(lib,)
    preamble = ['', '', '', function_parts[0]]
    #print(function_parts[0])
    function_parts = [preamble] + list(zip(
        function_parts[1::4], # return types
        function_parts[2::4], # name
        function_parts[3::4], # arguments (comma separated) # TODO: handle newlines?
        function_parts[4::4], # body and after body
    ))
    functions = []
    for rtype, name, args, body in function_parts:
        reps = []
        for a,b in replacements:
            if isinstance(a,str):
                new_body = body.replace(a,str(b))
            else:
                new_body = a.sub(str(b), body)
                a = str(a)
            if new_body != body:
                reps.append(a)
                body = new_body
        #if reps:
            #print("Function {} has replacements for:\n    {}".format(
                #name or 'preamble', '\n    '.join(reps)))
        for a,b in argument_replacements:
            args = args.replace(a,str(b))
        if not name: # preamble
            functions.append(body)
        else:
            functions.append("\n{} {}({}){}".format(rtype, name, args, body))
    return ''.join(functions)


SHADER_LIB = ""
debug_lib = False

def set_shader_lib(fragment='', mat=None, scn=None):
    global SHADER_LIB
    if not SHADER_LIB or debug_lib:
        if not fragment:
            if mat and scn:
                import gpu
                fragment = gpu.export_shader(scn, mat)['fragment']
            else:
                raise Exception("Wrong arguments")
        print('Converting shader lib')
        parts = fragment.rsplit('}',2)
        SHADER_LIB = \
"""#extension GL_OES_standard_derivatives : enable
#ifdef GL_ES
#extension GL_EXT_shader_texture_lod : enable
precision highp float;
precision highp int;
#ifndef GL_EXT_shader_texture_lod
vec4 texture2DLodEXT(sampler2D t, vec2 c, float level){
    return texture2D(t, c, 1.0+level);}
vec4 textureCubeLodEXT(samplerCube t, vec3 c, float level){
    return textureCube(t, c, 2.0+level);}
#endif
#endif
#define CORRECTION_NONE""" \
        +(parts[0]+'}').replace('\r','')+'\n'
        SHADER_LIB = do_lib_replacements(SHADER_LIB).encode('ascii', 'ignore').decode()
        splits = SHADER_LIB. split('BIT_OPERATIONS', 2)
        if len(splits) == 3:
            a,b,c = splits
            SHADER_LIB = a+'BIT_OPERATIONS\n#endif'+c
        if debug_lib:
            open('/tmp/shader_lib.orig.glsl','w').write((parts[0]+'}').replace('\r','')+'\n')
            open('/tmp/shader_lib.glsl','w').write(SHADER_LIB)

def get_shader_lib():
    return SHADER_LIB