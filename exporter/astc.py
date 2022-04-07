import os, zipfile, subprocess, tempfile
try:
    import requests
    has_requests = True
except:
    has_requests = False
    import traceback
    print(traceback.format_exc())
    print("WARNING: There was an error when loading requests")

ASTC_RGBA_FORMATS = {
    '4x4': 0x93B0,'5x4': 0x93B1,'5x5': 0x93B2,'6x5': 0x93B3,'6x6': 0x93B4,
    '8x5': 0x93B5,'8x6': 0x93B6,'8x8': 0x93B7,'10x5': 0x93B8,'10x6': 0x93B9,
    '10x8': 0x93BA,'10x10': 0x93BB,'12x10': 0x93BC,'12x12': 0x93BD}

ASTC_SRGB_FORMATS = {
    '4x4': 0x93D0,'5x4': 0x93D1,'5x5': 0x93D2,'6x5': 0x93D3,'6x6': 0x93D4,
    '8x5': 0x93D5,'8x6': 0x93D6,'8x8': 0x93D7,'10x5': 0x93D8,'10x6': 0x93D9,
    '10x8': 0x93DA,'10x10': 0x93DB,'12x10': 0x93DC,'12x12': 0x93DD}

plugin_dir = os.path.realpath(__file__).rsplit(os.sep,2)[0]
if os.name == 'nt':
    astc_binary = os.path.join(plugin_dir,'bin','astcenc','win64','astcenc-avx2.exe')
elif os.uname().sysname == 'Linux':
    astc_binary = os.path.join(plugin_dir,'bin','astcenc','linux64','astcenc-avx2')
elif os.uname().machine == 'arm64':
    astc_binary = os.path.join(plugin_dir,'bin','astcenc','mac-arm','astcenc-neon')
else:
    astc_binary = os.path.join(plugin_dir,'bin','astcenc','mac-intel','astcenc-avx2')

def get_astc_format_enum(mode, is_sRGB):
    if is_sRGB:
        return ASTC_SRGB_FORMATS[mode]
    else:
        return ASTC_RGBA_FORMATS[mode]

def encode_astc(in_path, out_path, mode, quality, is_sRGB):
    # quality: veryfast fast medium thorough exhaustive
    process = subprocess.Popen([astc_binary, '-cs' if is_sRGB else '-cl',
        in_path, out_path, mode, '-'+quality
    ])
    process.wait()
    if process.returncode != 0:
        raise Exception(' '.join([str(x) for x in ["astcenc failed with return code",process.returncode,"when encoding",in_path]]))
