import os, subprocess, tempfile, shutil, gzip

COMPRESSED_R11_EAC                        = 0x9270
COMPRESSED_SIGNED_R11_EAC                 = 0x9271
COMPRESSED_RG11_EAC                       = 0x9272
COMPRESSED_SIGNED_RG11_EAC                = 0x9273
COMPRESSED_RGB8_ETC2                      = 0x9274
COMPRESSED_SRGB8_ETC2                     = 0x9275
COMPRESSED_RGB8_PUNCHTHROUGH_ALPHA1_ETC2  = 0x9276
COMPRESSED_SRGB8_PUNCHTHROUGH_ALPHA1_ETC2 = 0x9277
COMPRESSED_RGBA8_ETC2_EAC                 = 0x9278
COMPRESSED_SRGB8_ALPHA8_ETC2_EAC          = 0x9279

plugin_dir = os.path.realpath(__file__).rsplit(os.sep,2)[0]
# TODO: detect platform
etcpak_binary = os.path.join(plugin_dir,'bin','etcpak.exe')

def encode_etc2_fast(in_path, out_path, sRGB, use_alpha):
    cwd = os.getcwd()
    temp = tempfile.gettempdir()
    os.chdir(temp)
    try:
        os.unlink(os.path.join(temp, 'out.pvr'))
        os.unlink(os.path.join(temp, 'outa.pvr'))
    except: pass
    if use_alpha:
        process = subprocess.Popen([etcpak_binary, in_path, '-etc2', '-m'])
        out = 'outa.pvr'
    else:
        process = subprocess.Popen([etcpak_binary, in_path, '-etc2', '-m', '-a'])
        out = 'out.pvr'
    process.wait()
    os.chdir(cwd)
    if process.returncode != 0:
        raise Exception(' '.join([str(x) for x in
            ["etcpak failed with return code",process.returncode,"when encoding",in_path]]))
    shutil.move(os.path.join(temp, out), out_path)
    # compress
    with open(out_path, 'rb') as f_in, gzip.open(out_path+'.gz', 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)

def get_etc2_format_enum(sRGB, use_alpha):
    # NOTE: Doesn't detect if etcpak wrote without alpha! (see above)
    if use_alpha:
        format = COMPRESSED_SRGB8_ALPHA8_ETC2_EAC if sRGB else COMPRESSED_RGBA8_ETC2_EAC
    else:
        format = COMPRESSED_SRGB8_ETC2 if sRGB else COMPRESSED_RGB8_ETC2
    return format
