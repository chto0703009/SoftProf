#!/usr/bin/env python3
# Copyright (c) 2026 Christer Törnkvist <christer@borgasundsfotografiska.se>
# SPDX-License-Identifier: GPL-3.0-or-later
"""JSON worker for the Python macOS soft-proof viewer (LittleCMS via Pillow)."""
import io
import hashlib
import os
import shutil
import tempfile
import json
import sys
import signal
from pathlib import Path
from PIL import Image, ImageCms, ImageOps
from icc_processing import process, profile_mode, save_image


class MissingSourceProfile(ValueError):
    """An untagged image requires the user's explicit source interpretation."""


def load_profile(path):
    if path == 'srgb':
        return ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
    raw = Path(path).read_bytes()
    profile = ImageCms.ImageCmsProfile(io.BytesIO(raw))
    profile.inkprof_original_bytes = raw
    return profile


def describe(profile):
    return ImageCms.getProfileDescription(profile).strip()


def load_image(path, source_path=None):
    with Image.open(path) as opened:
        if getattr(opened, 'n_frames', 1) != 1:
            raise ValueError('Bilder med flera sidor eller bildrutor stöds inte.')
        # Pillow can expose 16-bit multichannel files as RGB after reducing
        # their samples. Check file-level precision before decoding pixels.
        if opened.format == 'TIFF':
            bits = opened.tag_v2.get(258, (1,))
            bits = (bits,) if isinstance(bits, int) else bits
            high_depth = any(value > 8 for value in bits)
        elif opened.format == 'PNG':
            with open(path, 'rb') as stream:
                header = stream.read(26)
            high_depth = len(header) == 26 and header[24] > 8
        else:
            if opened.format=='JPEG' and getattr(opened,'bits',8)!=8:
                raise ValueError('JPEG-bilder stöds endast med 8 bitar per kanal. Använd TIFF eller PNG för 16 bitar.')
            high_depth = False
        if high_depth:
            from image16 import read_image16
            image=read_image16(path,opened)
        elif opened.mode == 'P' and opened.format == 'PNG':
            image = ImageOps.exif_transpose(opened).convert('RGBA' if 'transparency' in opened.info else 'RGB')
            image.load()
        elif opened.mode not in ('RGB', 'RGBA', 'CMYK', 'L', 'LA', 'LAB'):
            raise ValueError('Bildtypen stöds inte. Använd RGB, CMYK eller gråskala med 8 eller 16 bitar per kanal, eller 8-bitars Lab.')
        else:
            image = ImageOps.exif_transpose(opened)
            image.load()
    embedded = image.info.get('icc_profile')
    if embedded:
        source = ImageCms.ImageCmsProfile(io.BytesIO(embedded))
    elif source_path:
        source = load_profile(source_path)
    else:
        raise MissingSourceProfile('Bilden saknar ICC-profil. Välj en källprofil som beskriver bildens RGB-värden.')
    mode = {'RGBA': 'RGB', 'LA': 'L'}.get(image.mode, image.mode)
    if profile_mode(source) != mode:
        raise ValueError('Källprofilens färgrymd stämmer inte med bildens kanaler.')
    return image, source, bool(embedded)


def stage(image, source, working, intent, bpc):
    # Keeping the source space must not introduce a LUT round trip.
    if source.tobytes() == working.tobytes():
        return image.copy()
    return process(image, source, working, profile_mode(working), intent, bpc)


def previews(image, source, working, printer, display, intent, bpc, paper, ink=True, include_original=True):
    """Source -> working -> proof, with identical settings to saved conversion.

    Display is a tagged delivery space (Display P3), NOT the monitor profile.
    AppKit subsequently converts those tagged images to the current monitor.
    """
    original = process(image, source, display, 'RGB', 1, False) if include_original else None
    staged = stage(image, source, working, intent, bpc)
    if printer is None:
        return original, process(staged, working, display, 'RGB', 1, False)
    # Quantise to the same printer pixels as export before simulating paper.
    # A combined LCMS proof transform can select different LUT/optimisation
    # paths and does not include the exported 8-bit device quantisation.
    printed = process(staged, working, printer, profile_mode(printer), intent, bpc)
    # Preserve the printer black for ink/paper simulation. When both are
    # disabled, normalise device black to display black with viewing-leg BPC.
    # This viewing flag is independent of BPC in the exported conversion.
    proof = process(printed, printer, display, 'RGB', 3 if paper else 1, not (ink or paper))
    return original, proof


def run(request):
    render_entry=None
    if request.get('renderCache') and request.get('action') not in ('save','gamut'):
        inputs={k:request.get(k) for k in ('image','source','working','printer','display','intent','bpc','paper','ink','previewLimit')}
        image_stat=Path(request['image']).stat()
        inputs['fileIdentity']=(image_stat.st_ino,image_stat.st_size,image_stat.st_mtime_ns,image_stat.st_ctime_ns)
        for role in ('source','working','printer','display'):
            path=request.get(role)
            if path and path!='srgb':
                try: inputs[role]=hashlib.sha256(Path(path).read_bytes()).hexdigest()
                except OSError:
                    if role!='source': raise
                    # Embedded ICC takes precedence over an unavailable fallback.
                    inputs[role]='unavailable:'+str(path)
        cache_root=Path(request['renderCache']);cache_root.mkdir(parents=True,exist_ok=True)
        key=hashlib.sha256(json.dumps(inputs,sort_keys=True).encode()).hexdigest()
        render_entry=cache_root/('softprof-render-'+key)
        if render_entry.exists() and not (render_entry/'.softprof-entry').is_file():
            raise ValueError('Förhandsvisningens cachemapp tillhör inte SoftProf.')
        if (render_entry/'metadata.json').exists():
            try:
                result=json.loads((render_entry/'metadata.json').read_text())
                output=Path(request['output']);output.mkdir(parents=True,exist_ok=True)
                for name in ('original.png','proof.png'):shutil.copyfile(render_entry/name,output/name)
                os.utime(render_entry,None)
                return result
            except (OSError,ValueError): pass
    image, source, embedded = load_image(request['image'], request.get('source'))
    working = load_profile(request['working']) if request.get('working') else source
    printer = load_profile(request['printer']) if request.get('printer') else None
    intent, bpc = request.get('intent', 1), request.get('bpc', True)
    if intent not in (0, 1, 3):
        raise ValueError('Ogiltig återgivningsmetod.')
    metadata = dict(width=image.width, height=image.height, mode=image.mode, bits=getattr(image,'bits',8),
                    source=describe(source), embedded=embedded, working=describe(working),
                    printer=describe(printer) if printer else None)
    if request.get('action') == 'gamut':
        from gamut_analysis import analyze, colour_cloud
        analysis = analyze(image, source, working, printer, intent, bpc,
                           request.get('pixel'), request.get('gamutCache'))
        if request.get('cloud'):
            analysis['cloud'] = colour_cloud(image, source, working, printer, intent, bpc,
                                              display=load_profile(request['display']) if request.get('display') else None)
        if request.get('reference') and request.get('cloud'):
            reference = dict(request['reference'], action='gamut', cloud=True,
                             gamutCache=request.get('gamutCache'))
            reference.pop('reference', None)
            analysis['referenceCloud'] = run(reference)['cloud']
        return dict(ok=True, **metadata, **analysis)
    if request.get('action') == 'save':
        if printer is None:
            raise ValueError('Välj skrivarprofil före export.')
        staged = stage(image, source, working, intent, bpc)
        result = process(staged, working, printer, profile_mode(printer), intent, bpc)
        # Preserve the selected ICC file byte-for-byte. LittleCMS may rewrite
        # legacy description tags when a previously inspected profile is saved.
        if hasattr(printer, 'inkprof_original_bytes'):
            result.info['icc_profile'] = printer.inkprof_original_bytes
        save_image(result, request['destination'], request['image'], image.info.get('dpi'))
        return dict(ok=True, **metadata, destination=request['destination'])
    # Interactive approximation only; save and gamut return above at full resolution.
    limit = request.get('previewLimit', 0)
    if limit > 0:
        image.thumbnail((limit, limit), Image.Resampling.LANCZOS)
    display = load_profile(request['display'])
    # Cache only the setting-independent original preview. Its source, delivery
    # profile and file identity must match; conversion/export precision is intact.
    cached=None
    if request.get('originalCache'):
        stat=Path(request['image']).stat()
        key=hashlib.sha256(str((str(Path(request['image']).resolve()),stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns,request.get('previewLimit',0))).encode()+source.tobytes()+display.tobytes()).hexdigest()
        directory=Path(request['originalCache']); directory.mkdir(parents=True,exist_ok=True)
        cached=directory/(key+'.png')
    hit=cached is not None and cached.exists()
    # Preview transforms operate on the reduced image when requested.
    original, proof = previews(image, source, working, printer, display, intent, bpc,
                               request.get('paper', False), request.get('ink', True),include_original=not hit)
    folder = Path(request['output'])
    folder.mkdir(parents=True, exist_ok=True)
    for name, preview in [('original', original), ('proof', proof)]:
        if preview is None:
            shutil.copyfile(cached,folder/'original.png'); continue
        preview.save(folder / (name + '.png'), icc_profile=display.tobytes(),compress_level=1)
        if name=='original' and cached is not None:
            fd,temporary=tempfile.mkstemp(dir=cached.parent,suffix='.tmp'); os.close(fd)
            try:
                shutil.copyfile(folder/'original.png',temporary);os.replace(temporary,cached)
            finally:
                if os.path.exists(temporary):os.unlink(temporary)
    result=dict(ok=True, **metadata, previewWidth=proof.width, previewHeight=proof.height)
    if render_entry is not None:
        temporary=Path(tempfile.mkdtemp(dir=render_entry.parent,prefix='.pending-'))
        try:
            for name in ('original.png','proof.png'):shutil.copyfile(folder/name,temporary/name)
            (temporary/'metadata.json').write_text(json.dumps(result))
            (temporary/'.softprof-entry').write_text('SoftProf preview cache v1')
            if render_entry.exists():shutil.rmtree(render_entry)
            temporary.rename(render_entry)
            entries=sorted((p for p in render_entry.parent.iterdir() if p.is_dir() and p.name.startswith('softprof-render-') and (p/'.softprof-entry').is_file()),key=lambda p:p.stat().st_mtime_ns,reverse=True)
            for old in entries[6:]:shutil.rmtree(old,ignore_errors=True)
        finally:
            if temporary.exists():shutil.rmtree(temporary,ignore_errors=True)
    return result


def terminate_worker(signum, frame):
    # Unwind save_image's finally block rather than abandoning an export file.
    raise SystemExit(128 + signum)


def main():
    signal.signal(signal.SIGTERM, terminate_worker)
    request_path, response_path = map(Path, sys.argv[1:3])
    try:
        response = run(json.loads(request_path.read_text()))
    except Exception as error:
        response = dict(ok=False, error=str(error))
        if isinstance(error, MissingSourceProfile): response['code'] = 'missing_source_profile'
    response_path.write_text(json.dumps(response, ensure_ascii=False))
    return 0 if response['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
