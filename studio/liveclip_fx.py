"""Local clip post-processing: time-scoped webcam reaction zooms and quiet background music.
No cloud calls or heavyweight ML needed. Automatic peaks are *heuristics*, not semantic scene detection.
"""
from array import array
import math
import statistics
import subprocess
import sys
from pathlib import Path


def automatic_reactions(src: Path, start: float, end: float, *, ffmpeg='ffmpeg', no_window=0, factor=1.6):
    """Return up to 3 1.8s reaction windows using relatively loud audio moments.
    If no distinct peaks are present, return [] rather than fabricating emotional moments.
    """
    duration = end - start
    if duration < 7:
        return []
    cmd = [ffmpeg, '-v', 'error', '-ss', f'{start:.3f}', '-t', f'{duration:.3f}', '-i', str(src),
           '-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', 'pipe:1']
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=min(80, 8 + duration * 0.8), creationflags=no_window)
        if result.returncode or len(result.stdout) < 32000:
            return []
        samples = array('h')
        samples.frombytes(result.stdout[:len(result.stdout) - (len(result.stdout) % 2)])
        if sys.byteorder != 'little': samples.byteswap()
        step = 2000  # 0.25s at 8kHz
        vals = []
        for i in range(0, len(samples) - step, step):
            # decimate for cheap yet stable RMS; also avoids numpy dependency
            chunk = samples[i:i + step:4]
            vals.append(math.sqrt(sum(x*x for x in chunk)/len(chunk)) / 32768)
        if len(vals) < 20: return []
        baseline = statistics.median(vals)
        if baseline < 0.004: return []
        ranked = sorted(range(5, len(vals) - 5), key=lambda i: vals[i], reverse=True)
        found = []
        for i in ranked:
            # Significant bursts compared with typical level and surrounding 2 seconds.
            local = statistics.median(vals[max(0, i - 8):min(len(vals), i + 9)])
            if vals[i] < max(0.08, baseline * 1.85, local * 1.45): continue
            center = i * .25
            left = max(0, center - .35)
            right = min(duration, left + 2.0)
            if right - left < 1.3: continue
            if any(abs(center - (z['start']+z['end'])/2) < 7 for z in found): continue
            found.append({'start': round(left, 2), 'end': round(right, 2), 'scale': factor})
            if len(found) >= min(3, max(1,int(duration//14))): break
        return sorted(found, key=lambda z:z['start'])
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return []


def add_reaction_zooms(fc: str, source: str, events: list, *, width: int, height: int,
                       facecam, pip_width: int, pip_height, pip_x, pip_y, pip_side,
                       bg_mode='none', bg_video_scale=86):
    """Return filterchain and final label with webcam close-ups ABOVE the gameplay.
    Captions are applied by the caller AFTER this, so text never gets distorted.
    """
    if not events or not facecam or len(facecam)!=4:
        return fc, source
    fw, fh = float(facecam[2]), float(facecam[3])
    if fw <= 8 or fh <= 8: return fc, source
    pw = min(width,max(20,int(pip_width)))
    ph = min(height,max(20,int(pip_height) if pip_height is not None else int(pw*fh/fw)))
    x = int(pip_x) if pip_x is not None else (26 if pip_side=='left' else (width-pw)//2 if pip_side=='center' else width-pw-26)
    y = int(pip_y) if pip_y is not None else 26
    if bg_mode=='gta6':
        ratio = min(.98, max(.70, float(bg_video_scale)/100))
        x = int((width-width*ratio)/2 + x*ratio)
        y = int((height-height*ratio)/2 + y*ratio)
        pw,ph = int(pw*ratio),int(ph*ratio)
    x=max(0,min(width-4,x));y=max(0,min(height-4,y))
    pw=max(4,min(pw,width-x));ph=max(4,min(ph,height-y))
    # Build one split for all events, to avoid re-zooming previous reactions.
    fc += f'[{source}]setpts=PTS-STARTPTS,split={len(events)+1}' + ''.join(f'[zf{i}]' for i in range(len(events))) + '[zbase0];'
    for i,z in enumerate(events):
        # A little crop within the facecam produces a true close-up of the face rather than scaling the frame.
        factor=max(1.1,min(2.5,float(z.get('scale',1.6))))
        cropw=max(2,int(pw/factor)//2*2); croph=max(2,int(ph/factor)//2*2)
        cx=(max(0,min(width-cropw, x+(pw-cropw)//2))//2)*2
        cy=(max(0,min(height-croph,y+(ph-croph)//2))//2)*2
        # Preserve source aspect; never squash the webcam face.
        targetw=(min(width-32,max(pw+60,int(pw*1.4)))//2)*2
        targeth=(min(int(height*.48),max(2,int(targetw*croph/cropw)))//2)*2
        if targeth<2: continue
        st=max(0,float(z['start']));en=max(st+.5,float(z['end']))
        fin=min(.22,(en-st)/4)
        fc += (f'[zf{i}]crop={cropw}:{croph}:{cx}:{cy},scale={targetw}:{targeth}:flags=lanczos,'
               f'format=yuva420p,fade=t=in:st={st:.3f}:d={fin:.3f}:alpha=1,'
               f'fade=t=out:st={en-fin:.3f}:d={fin:.3f}:alpha=1,'
               f'drawbox=x=0:y=0:w=iw:h=ih:color=0x9a5dff@0.9:t=3[up{i}];'
               f'[zbase{i}][up{i}]overlay=(W-w)/2:{int(height*.04)}:shortest=1:'
               f"enable='between(t,{st:.3f},{en:.3f})'[zbase{i+1}];")
    return fc, f'zbase{len(events)}'


# LiveClipAI_Musica_Audivel_V2: mix corrigido
def mix_music_filters(duration: float, input_index: int, music_level: float) -> str:
    """Background audible with consistent perceived volume. Never replaces the stream audio.

    The bundled track averages -24.6 dBFS. Without normalization, multiplying by 0.18
    makes it very quiet compared with loudnorm -14 LUFS speech and gameplay.
    Music is normalized separately, then scaled on a perceptual reference and mixed
    without amix input normalization. Both streams begin at zero and fade cleanly.
    """
    duration = max(0.1, float(duration))
    level = max(0.0, min(0.65, float(music_level)))
    fadeout = min(0.9, duration / 6)
    fadein = min(0.45, duration / 6)
    gain = level * 1.70
    return (
        f'[0:a:0]asetpts=PTS-STARTPTS,loudnorm=I=-14:TP=-1.5:LRA=11[speech];'
        f'[{input_index}:a:0]atrim=duration={duration:.3f},asetpts=PTS-STARTPTS,'
        f'loudnorm=I=-16:TP=-2:LRA=9,volume={gain:.4f},'
        f'afade=t=in:st=0:d={fadein:.3f},'
        f'afade=t=out:st={max(0, duration - fadeout):.3f}:d={fadeout:.3f}[bgmusic];'
        '[speech][bgmusic]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,'
        'alimiter=limit=0.94[audioout]'
    )

