# SoftProf

User guide - version 2.5.2 - 7 November 2026

Christer Törnkvist - christer@borgasundsfotografiska.se
GNU GPL version 3 or later (GPL-3.0-or-later).

## 1. Install and get started

SoftProf compares an image with a prediction of its printed appearance. It helps you explore the consequences of a working colour space, printer/paper ICC profile, rendering intent and black point compensation before exporting a converted image.

### Install the app

Open `SoftProf-2.5.2-macos.dmg`, choose **Apple Silicon** or **Intel** to match your Mac and drag that app to **Applications**, eject the disk image and launch the app from Applications. The DMG contains two labelled apps: **Apple Silicon requires macOS 14+; Intel requires macOS 13 Ventura+**. Apple Silicon is ARM64; Intel is x86_64. All bundled Intel binaries are checked against the Ventura deployment target. Physical Ventura hardware has not been tested here. Install only the matching app. Python and the required libraries are included; the development project is not needed.

The package is ad hoc signed, but not Developer ID signed or Apple-notarized. If macOS blocks the first launch, review it in **System Settings > Privacy & Security > Open Anyway**. The DMG includes both manuals, the GPL license and application source.

### Choose the app for your Mac

| Computer | App and badge |
| --- | --- |
| Apple Silicon, such as M1, M2 or M3 | SoftProf - Apple Silicon.app, ARM64 badge |
| Intel processor | SoftProf - Intel.app, INTEL badge |

Check **Apple menu > About This Mac** if unsure. Install one app. ARM64 runs natively without Rosetta on Apple Silicon; the Intel app runs natively on an Intel Mac. Rosetta is used only in our Intel-build test on Apple Silicon.

The image dialog starts on Desktop and the ICC dialog in `/Library/ColorSync/Profiles`. They then remember their last selected folders separately.

### Start with a known image

Choose **Open image**, then a tab. **1 Colour spaces** compares the original with a chosen working space. **2 Printer profiles** compares the original with a printer profile, or two printer profiles. For an untagged image, a dialog asks you to choose its actual source profile or a custom ICC file, then click **Show image**. Cancel leaves the source selector available; the source selector is hidden when an embedded ICC is available.

<!-- pipeline -->

The tabs use separate paths: **source > working space**, or **source > printer profile**. Printer comparisons do not use the working-space selection from the other tab. A separate display conversion prepares the proof for the screen; macOS ColorSync adapts the tagged preview to the current monitor.

### Keep the physical setup consistent

Use the ICC profile for the actual printer, paper, ink and driver settings. The monitor, its calibration and the light used to view a print affect the comparison. Soft proofing is a profile-based estimate, not a measurement or a guarantee of a matching print.

## 2. Profiles and rendering

### Source profile and working colour space

In **1 Colour spaces**, choose **Working space** to explore sRGB, Adobe RGB, Display P3, ProPhoto RGB or a custom ICC profile. The gamut window shows source and working colours. In **2 Printer profiles**, choose the printer/paper ICC profile; the gamut window shows source and print colours.

An embedded ICC profile is always used as the source. For an image without a profile, select the profile that actually describes its stored values. Assigning that interpretation does not change the original file. Choosing the wrong source profile changes the meaning of every colour.

The working-space menu offers sRGB, Adobe RGB (1998), Display P3, ProPhoto RGB and a custom ICC file. ProPhoto RGB uses the macOS ROMM RGB system profile. **Keep the image colour space** avoids an unnecessary working-space round trip. Rendering intent and BPC apply to the conversion in the active tab. Paper-white and black-ink simulation are available only in Printer profiles.

| Rendering intent | Practical interpretation |
| --- | --- |
| Relative colorimetric | Adapts white to the destination and maps colours outside its gamut. |
| Absolute colorimetric | Preserves absolute colourimetry, including the profile's white-point relationship. |
| Perceptual | Uses the profile's perceptual mapping, when provided, to preserve visual relationships. |

Different intents can produce the same result when the profile does not provide distinct mappings.

### Black point compensation and paper white

**Black point compensation** adjusts the mapping of dark tones between profiles. Its visible effect depends on the profiles and rendering intent.

**Simulate paper white** is a separate screen-proof setting. It selects absolute colorimetric proof-to-display rendering; the selected printer conversion intent remains a separate stage. This setting affects the preview, not the saved printer pixels.

**Simulate black ink** preserves the printer profile’s predicted black. Turn it off, with paper white off, to map black to screen black. Paper-white simulation also enables black-ink simulation. These viewing choices do not change export. The preview uses the same 8- or 16-bit conversion pipeline on reduced pixels, so fine details and mixed colours may differ from full-resolution export; LittleCMS optimisation is disabled to avoid extra interpolation errors. JPEG export can introduce additional changes.

### Screen colour management

Previews are ICC-tagged Display P3 images shown through macOS AppKit/ColorSync. The operating system adapts them to the monitor displaying the window, including when the window changes screens. Do not select the monitor profile as a working or printer profile. Display P3 itself can limit colours beyond that intermediate space.

## 3. Compare and select a colour

### Side-by-side comparison

Both tabs start with the original on the left. In Colour spaces, the right shows the selected working space. In Printer profiles, the right shows the selected printer/paper simulation. Each tab keeps its own settings while you switch. In Colour spaces, the left image is always the original. Working space, rendering intent and BPC are grouped above the right image. Only Printer profiles can lock a reference; opening a new image clears it.

In Colour spaces, change the controls above the right image to compare their effect against the unchanged original on the left. In Printer profiles, use **Compare with another profile…** to lock the current simulation and select a second printer profile. The reference caption preserves its settings. **Reset left to original** restores the source image on the left while keeping the current right-hand profile and settings.

Captions identify each profile and its settings. Further changes affect the right while the left stays locked.

In Printer profiles, **Swap left ↔ right** exchanges the two simulations together with their profiles, working space, rendering intent, BPC and paper/ink settings. The right side remains editable; the left stays locked. Swapping twice restores the starting comparison.

### Zoom and scroll

Both views share zoom and scrolling. **Fit** shows the whole image. Interactive previews are reduced to at most 1600 pixels on the longest side before ICC processing. The 25%, 50% and 100% settings use original dimensions but enlarge this reduced preview; they do not show full-resolution detail. Export and clicked-pixel analysis use the original image.

Recent preview settings are cached during the session (up to six completed views). Returning to a cached setting skips source-image decoding and ICC processing. The unchanged original preview is reused, and PNG preview compression is faster but remains lossless. New settings process the reduced preview. Export still processes the original at full resolution.

The **Gamut…** button is directly below the right-hand image. **Convert and save…** is at the far right of that row.

### Click-to-sample

Click either image to open the gamut window and follow the corresponding original pixel. A crosshair marks the location in both views. The sample is read from the original file after EXIF orientation, independently of preview reduction and zoom.

Clicking a locked reference still follows that original pixel through the **current** profile settings. It does not sample the reference's old conversion. Changing settings updates the same selected pixel. Selecting a new image clears the reference and sample.

### Read the stage values

The gamut window reports source and working-space values in the first tab, and source and predicted printer values in the second. RGB or CMYK channel numbers may change while the Lab position stays almost unchanged: a colour-preserving conversion aims to keep the colour, not the same numbers. A movement indicates a predicted colour change, for example from gamut mapping or quantisation.

## 4. Read the gamut diagram

All profiles are compared in **CIELAB D50**. The default 2D diagram shows the a*/b* plane from above. Axis units use a common scale, expanding when necessary without shrinking as settings change.

<!-- gamut -->

### Contours, points and arrows

Contours show the profiles in the active tab. Numbered points and arrows follow **original > working space** or **original > predicted print**. Toggle contours separately to reduce clutter. Grey rings show the previous settings for the same pixel.

The numerical rows show L*, a*, b*, device-channel values and **ΔE76 from the original**. Lab is evaluated through LittleCMS with floating-point output and fixed absolute D50 colourimetry. Device-channel conversions follow the same 8- or 16-bit pipeline as export. The printer point is the profile's prediction, not a measured print. The screen profile and paper-white preview toggle are not part of these analysis coordinates.

### Approximate colour background

**Colour-tinted background** supplies a hue guide; **Strength** adjusts its visibility. Turn off **Follow sample L*** to choose background lightness from **0 to 100** with the slider or numeric field (press Enter). L* 0 is black and 100 is white. Turn it on to follow the original sample's L*, or 65 before selection. This changes only the approximate background, not samples, contours or export. The background is a coloured slice at the chosen L* behind the projected contours, not a measurement of all colours in that projection. Display clipping and tinting make the background approximate.

### Do not use outlines as an exact gamut test

Contours are convex outer envelopes of sampled ICC device values, projected onto a plane. They merge the third dimension and may overestimate concave regions. Sampling uses 17 levels per RGB/Lab channel and 9 per CMYK channel, without a separate CMYK total-ink limit. A point inside a contour does not prove that the colour is printable at its L*.

L*, a*, b* and Delta E use fixed aligned columns. Plot drawing stays within its frame during zooming and window resizing.

## 5. 3D colour space

Choose **Show 3D colour space**; **Show 2D** restores the existing diagram. Choose **Original** and **Working space** in the first tab, or **Original** and **Print** in the second. Drag the plot to rotate, scroll to zoom, or choose **Reset 3D view**. L* increases upwards towards lighter colours, a* runs from green (negative) to red (positive), and b* from blue (negative) to yellow (positive). Follow the labelled axes after rotating the view. The selected image pixel is marked with a white ring in the chosen stage. The L* background controls apply only to 2D.

Enable **Show movement** for yellow arrows. In **Printer profiles**, arrows always run **original > predicted print**, regardless of which point set is selected: the tail is the original colour and the arrowhead is the predicted print. In **Colour spaces**, arrows compare previous and new positions as settings or displayed stages change. Paper-white and ink viewing toggles do not alter absolute Lab positions.

Faint, thin arrows represent rare colours; stronger arrows represent more frequent colours in the sampled image. Arrow length shows the colour difference, not frequency. No colour groups are hidden by this weighting. Long arrows can come from a few highly saturated colours that the printer cannot reproduce; they do not mean that most of the image changes that much.

**Compare left → right** compares a locked left simulation with the current right simulation. Points always show the right-hand colours. A yellow arrow starts at each corresponding left-hand position and ends at the right-hand point. Small arrowheads keep the points visible; reference rings are omitted. The short caption identifies both profiles. Swapping the images reverses this comparison. Resetting the left image clears the locked-reference comparison. These are absolute D50 profile colours; paper/ink screen simulation does not change their coordinates.

The 3D view shows up to 1,024 frequent groups from at most 65,536 deterministic stratified pixel samples. Nearby source channel values share a group; an actual source pixel represents each group. The smaller points improve visibility in dense regions; point size still increases with approximate sampled frequency; fully transparent pixels are omitted and partial alpha weights frequency. Rare colours may be omitted. The points are an image distribution, not a solid profile-gamut shell. Their Display P3 screen colours are approximate. Original photographs are unchanged.

<!-- cloud -->

## 6. Export and print

Choose **Convert and save** after selecting an image and printer/paper profile. Saving is available in Printer profiles. The app processes the full original directly from its source profile to the right-hand printer profile, then embeds the selected printer ICC file **byte for byte**. The source image cannot be overwritten. New files follow the system umask; replacing an existing export preserves its permission bits. A temporary file is completed before replacing the destination.

| Format | Supported output channels |
| --- | --- |
| TIFF | RGB, RGBA, CMYK, greyscale, greyscale with alpha, Lab |
| PNG | RGB, RGBA, greyscale, greyscale with alpha |
| JPEG | RGB, CMYK, greyscale; no alpha; lossy compression |

An incompatible channel/format combination is rejected rather than silently changed. Transparency can be retained through RGB or greyscale processing; CMYK/Lab conversion with alpha is rejected. Transparent colour samples are analysed before compositing with a background, and their alpha is shown separately.

### Print the converted values once

The exported image is already converted to the printer profile. Print these values with further application, operating-system and driver colour conversion disabled. Use the same printer, paper, media and quality settings as the ICC profile. The app exports files; it does not control or verify the printer driver or physical print chain.

### Version limits

Indexed PNGs are expanded to RGB/RGBA with their ICC profile and transparency retained. The app supports one image frame and **8 or unsigned 16 bits per channel**. For 16-bit images, RGB/RGBA and grayscale/alpha use TIFF or PNG; CMYK uses TIFF. TIFF supports uncompressed, LZW, Deflate/ZIP and PackBits data, separate planes and orientation. ICC conversion, selected pixels, 3D positions and TIFF/PNG export retain 16-bit precision. Values range from 0 to 65,535 instead of 0 to 255. JPEG is 8-bit only and cannot be chosen for 16-bit sources. File-based 16-bit Lab and 32-bit/floating-point images are unsupported; a Lab working profile is still supported. Export retains pixel dimensions, ICC, DPI and supported alpha, not all EXIF/XMP. Paper and ink simulation are not baked into export.

A successful export or small predicted ΔE is not evidence of measured print accuracy. Assess important work with a correctly prepared physical test print.

A synthetic numerical comparison with Photoshop 27.11 found and corrected a dark-tone optimisation error. Remaining differences are documented in the GitHub colour-validation report. This is not a verification of Photoshop’s on-screen Proof Colors or physical print accuracy.

## 7. Language, architecture and license

### Language and exit

Select **Svenska** or **English** at **Språk / Language**. Both windows, menus, status messages and application errors update immediately. Profile choices, the selected pixel and locked reference are preserved. The choice is restored on the next launch. Profile names and filenames are not translated; macOS-owned buttons and system errors may follow the system language.

**Quit** is at the bottom right of the main window. You can also use the app menu or Command-Q. Normal Quit waits for an active export to finish. A worker terminated with SIGTERM removes its temporary export file; force-kill or power loss cannot guarantee cleanup.

### ARM, Intel and Rosetta

The bottom status area distinguishes computer hardware, the Python process architecture and native or Rosetta execution. Rosetta is queried inside the Python process. Unavailable information is reported as **Unknown**, rather than guessed. Native ARM, native Intel and Rosetta classifications are tested; the DMG contains separate ARM64 and x86_64 apps with strict binary audits. ARM64 is tested natively; Intel is tested via Rosetta on Apple Silicon, not on a physical Intel Mac.

### GPL license and contact

Copyright (c) 2026 **Christer Törnkvist**.
Email: **christer@borgasundsfotografiska.se**.

The application and documentation are free software under the **GNU General Public License, version 3 or any later version** (GPL-3.0-or-later). They are provided without warranty. The full unmodified license is in **LICENSE**. Third-party code, system resources and fonts retain their own terms; see **LICENSE_SCOPE.md** and **THIRD_PARTY_NOTICES.md**.

The app menu offers **About SoftProf** with author, contact and license information, and **View the GPL license** opens the full text. The DMG includes application source, build tools and both manuals. The English README explains source installation, tests and rebuilding the DMG. No personal photographs, measurements or local virtual environments are included in the Git repository or source archive.

---

GitHub: [chto0703009/SoftProf](https://github.com/chto0703009/SoftProf)
