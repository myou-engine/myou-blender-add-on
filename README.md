# Introduction
Myou Blender Plugin allows you to export Blender scenes, meshes, materials (GLSL), textures and animations to be used in your Myou Engine project.

You can use any 3D model or texture formats supported by Blender (natively or using addons). But those assets must be optimal enough to have good performance in Myou Engine.

To have optimized assets you can import, edit or create any material, mesh and texture in Blender using some Blender features such as mesh modifers,  material nodes or physics properties among many others.

# Installing Myou Blender Plugin

- Install [Blender 2.71](http://download.blender.org/release/Blender2.71/) (future versions are likely to work but not guaranteed).

- Download Myou blender plugin in ZIP format from "clone or download" in github, or use [this link](https://github.com/myou-engine/myou-blender-plugin/archive/master.zip)

- In Blender, click File -> User Preferences -> Addons

- Click "Install from File..." and find and click the downloaded ZIP file

- Then enable the plugin by clicking on the checkbox at the left of "Game Engine: Myou game engine" that appeared there

- Save User Settings.

Alternatively you can clone this repository and link it to the Blender addons folder (see "Development" section).

# Meshes

Myou Blender Plugin applies most Blender modifiers before exporting the meshes and you are free to use them, only having in mind some considerations.

 - If you are using linked copies, only the modifiers of the first copy will be applied to the mesh.
 - Meshes with more than ~64k vertices will require a lot of time to be exported, decimate the number of polygons or split them in several objects.
 - _Armature_ modifiers will not be applied on exporting, Myou will manage the armature deformations. Make sure it's at the bottom of the stack for correct preview. It has a limit of about 65 bones and doesn't support "Preserve Volume" nor "Bone envelopes".

## LoD meshes
You can also generate alternative meshes with different level of detail (LoD) to use them in the engine, which will be automatically generated on exporting using _Decimate_ modifier (any modifier works for this, but _Decimate_ is the most common for this task).

### Naming rules
Only modifiers whose name start with `lod-` will be processed by the exported as LoD meshes. Notice that `-` can be replaced by any non alphanumeric character.

Examples: `lod`, `lod.001`, `lod_simple`, `lod and any other words`

### Embed LoD meshes
You can mark a LoD modifier to be exported embed in the scene to be loaded in you project during the scene loading process by adding `embed-` to the name of the _Decimate_ modifier just after `lod-`.

Examples: `lod-embed`, `lod embed mesh`, `lod_embed_other_words`,

### Warnings
If you are using LoD the max number of vertices of the LoD mesh must be inferior to ~65k.

# Materials
GLSL Materials in Blender will be converted and exported directly to Myou. You can use any of the Blender material features, included material nodes.

# Textures
All texture format supported by Blender will automatically be converted to PNG/JPG in the export process. When the alpha channel of the texture is not being used, it will be exported to JPG, but if the alpha channel of the texture is being used by any material, the texture will be exported to PNG.

We are working to add support to different gpu texture formats.

## LoD textures
You can set a texture to be exported to multiple level of detail versions in the exportation process.
To set a texture as LoD on exporting, you must add a custom property `lod_levels` to the texture.

The value of `lod_levels` will be a string or a list of resolutions expresed as an integer or a list of two elements [width, height]. The resolutions expressed as integers, will be exported using this value for both width and height.

Examples: `[32, 64, 128]`, `[ [16,32], [32,64], [64,128] ]`, `[32, 64, [128,256], 1024]`

## Embedded textures
All the textures that are 64x64 or lower resolution will be embed in the scene. To change the default 64x64 limit to be embed, you must add an ```embed_max_size``` custom property to the scene. The value of this property must be expressed as an integer.

## Limitations
Myou only accepts power of 2 texture resolutions. Also, if you use textures in iOS, make sure they're square.

# Development

To be able to change or update the plugin without creating a ZIP or copying files every time, find the addons folder (replace 2.78 by the current version if needed).

Windows
```
C:\Users\%username%\AppData\Roaming\Blender Foundation\Blender\2.71\scripts\addons
```

Linux
```
/home/$user/.config/blender/2.71/scripts/addons
```

Then link myou-blender-plugin to Blender addons folder. Replace `[Path to myou-blender-plugin]` to the full local path of the repository.

Windows (cmd or cygwin)
```
 cmd /c mklink /j "%APPDATA%/Blender Foundation/Blender/2.71/scripts/addons/myou-blender-plugin" "[Path to myou-blender-plugin]"
```

Linux
```
ln -s "[Path to myou-blender-plugin]" "/home/$user/.config/blender/2.71/scripts/addons"
```

### Reload

In Blender, press space, search "myou" and select "Reload Myou plugin". It will try to reload changes to the plugin. This feature may crash Blender so make sure to have your data saved.

### Blender 2.78 support
This blender version is currently supported, but materials are not being exported correctly. We are working to get full support to blender 2.78 as soon as posible. 

# WORK IN PROGRESS
