from pprint import *
import re

replacements = [
    ('''/* These are needed for high quality bump mapping */
#version 130
#extension GL_ARB_texture_query_lod: enable
#define BUMP_BICUBIC''',''),
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

    ('(normalize(vec).z + 1)', '(normalize(vec).z + 1.0)'),
    ('strength * v1 + (1 - strength) * v2', 'strength * v1 + (1.0 - strength) * v2'),
    ('int(x) - ((x < 0) ? 1 : 0)', 'int(x) - ((x < 0.0) ? 1 : 0)'),
    ('return x - i;', 'return x - float(i);'),
    ('(M_PI * 2)', '(M_PI * 2.0)'),
    ('((mod(xi, 2) == mod(yi, 2)) == bool(mod(zi, 2)))', 'true'),
    (re.compile(r'if \(depth > (\d)\) {'), r'if (depth > \1.0) {'),
    ('fac = 1;', 'fac = 1.0;'),
    ('outv = -v;','outv = vec3(0.0)-v;'),
    ('#extension GL_EXT_gpu_shader4: enable', ''),
    ('sampler1D', 'sampler2D'),
    ('texture1DLod(unflutsamples, (float(u) + 0.5) / float(BSDF_SAMPLES), 0.0).rg;', 'texture1DLod(unflutsamples, vec2((float(u) + 0.5) / float(BSDF_SAMPLES), 0.0)).rg;'),
    ('sampler2DShadow','sampler2D'), # part of argumenst but it doesn't handle \n well
]

argument_replacements = [
    ('sampler2DShadow','sampler2D'),
]

# Make sure \r are removed before calling this
def do_lib_replacements(lib):
    function_parts = re.compile(r"^(\w+)\s+(\w+)\s*\((.*)\)", flags=re.M).split(lib,)
    preamble = ['', '', '', function_parts[0]]
    function_parts = [preamble] + list(zip(
        function_parts[1::4], # return types
        function_parts[2::4], # name
        function_parts[3::4], # arguments (comma separated)
        function_parts[4::4], # body and after body
    ))
    functions = []
    for rtype, name, args, body in function_parts:
        reps = []
        for a,b in replacements:
            if isinstance(a,str):
                new_body = body.replace(a,b)
            else:
                new_body = a.sub(b, body)
                a = str(a)
            if new_body != body:
                reps.append(a)
                body = new_body
        if reps:
            print("Function {} has replacements for:\n    {}".format(
                name or 'preamble', '\n    '.join(reps)))
        for a,b in argument_replacements:
            print(args)
            args = args.replace(a,b)
            print(args)
        if not name: # preamble
            functions.append(body)
        else:
            functions.append("{} {}({}){}".format(rtype, name, args, body))
    return ''.join(functions)
