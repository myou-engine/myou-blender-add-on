import os, subprocess, tempfile, shutil, gzip, zipfile
# try:
#     import requests
#     has_requests = True
# except:
#     has_requests = False
#     import traceback
#     print(traceback.format_exc())
#     print("WARNING: There was an error when loading requests")

COMPRESSED_RGB_PVRTC_4BPPV1_IMG      = 0x8C00
COMPRESSED_RGB_PVRTC_2BPPV1_IMG      = 0x8C01
COMPRESSED_RGBA_PVRTC_4BPPV1_IMG     = 0x8C02
COMPRESSED_RGBA_PVRTC_2BPPV1_IMG     = 0x8C03

plugin_dir = os.path.realpath(__file__).rsplit(os.sep,2)[0]
# TODO: detect platform
crunch_binary = os.path.join(plugin_dir,'bin','crunch_x64.exe')
# compressonator_binary = os.path.join(plugin_dir,'bin','CompressonatorCLI_x64.exe')
# compressonator_is_downloaded = False

# # TODO: move to bcn.py
# def download_compressonator_if_needed():
#     if not has_requests:
#         print("Requests module not found")
#         return
#     if not os.path.exists(compressonator_binary):
#         print("Downloading Compressonator from github.com/GPUOpen-Tools")
#         # supplying our own cert root avoid an issue in linux and mac;
#         # an alternative that also works is looking for one of these files:
#         # /etc/ssl/certs/ca-bundle.crt
#         # /etc/ssl/certs/ca-certificates.crt
#         # TODO DANGER!!! VERIFY IS FALSE UNTIL REQUESTS WORK WITH SSL
#         req = requests.get('https://github.com/GPUOpen-Tools/Compressonator/releases/download/v3.1.4064/CompressonatorCLI_x64_3.1.4064.exe',
#             stream=True, verify=False)
#         if req.status_code != 200:
#             raise Exception("Error %i when downloading Compressonator from github" % req.status_code)
#         open(compressonator_binary, 'wb').write(req.raw.read())
#     if os.name != 'nt':
#         os.chmod(compressonator_binary, 0o777)
#     compressonator_is_downloaded = True

compressonator_binary = os.path.join(plugin_dir,'bin','CompressonatorCLI', 'CompressonatorCLI.exe')

def encode_s3tc(in_path, out_path, use_alpha):
    if os.path.exists(compressonator_binary):
        command = [compressonator_binary, '-miplevels', '99', '-fd', ]
        if use_alpha:
            command += ['DXT5']
        else:
            command += ['DXT1']
        process = subprocess.Popen(command+[in_path, out_path])
        process.wait()
        if process.returncode != 0:
            raise Exception(' '.join([str(x) for x in
                ["Compressonator failed with return code",process.returncode,"when encoding",in_path]]))
    else:
        cwd = os.getcwd()
        command = [crunch_binary, '-file', in_path, '-fileformat', 'dds',
        '-yflip']
        if use_alpha:
            command += ['-DXT5']
        else:
            command += ['-DXT1']
        if 0: # fast quality
            command += ['-dxtQuality', 'superfast']
        process = subprocess.Popen(command+['-out', out_path])
        process.wait()
        if process.returncode != 0:
            raise Exception(' '.join([str(x) for x in
                ["Crunch failed with return code",process.returncode,"when encoding",in_path]]))
    # compress
    with open(out_path, 'rb') as f_in, gzip.open(out_path+'.gz', 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)
