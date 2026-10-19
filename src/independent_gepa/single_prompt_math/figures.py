"""Standalone scientific figures from already measured, prefix-safe V6 events."""
from pathlib import Path
import xml.etree.ElementTree as ET

from .common import read,write,file_hash
from ..audit import SECRET_VALUE,WINDOWS_ABSOLUTE,POSIX_ABSOLUTE
from ..protocol import ProtocolViolation


def render(run,output,*,fake):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    matplotlib.rcParams['svg.hashsalt']='independent_gepa_v6'
    specs=[('validation_native','native_metric_calls','best_score','Native logical evaluations','Best Validation accuracy'),
           ('validation_tokens','search_tokens','best_score','Attributed total search tokens','Best Validation accuracy'),
           ('frontier_native','native_metric_calls','sampling_frontier_candidates','Native logical evaluations','Native sampling-frontier candidates'),
           ('nonbest_native','native_metric_calls','nonbest_parent_selections','Native logical evaluations','Cumulative strictly nonbest selections'),
           ('discoveries_native','native_metric_calls','new_best_discoveries','Native logical evaluations','Strict new-best discoveries')]
    curves={}
    for arm in ('strict_validation','native_pareto'):
        for repeat in (1,2,3):
            path=run/arm/f'repeat_{repeat}'/'mechanism_events.json'
            curves[(arm,repeat)]=read(path)
    output.mkdir(parents=True,exist_ok=True)
    for name,x,y,xlabel,ylabel in specs:
        fig,ax=plt.subplots(figsize=(8,4.8),layout='constrained')
        for (arm,repeat),events in curves.items():
            points=[r for r in events if r[y] is not None]
            ax.step([r[x] for r in points],[r[y] for r in points],where='post',
                color='#2864b4' if arm=='strict_validation' else '#ce6434',
                linestyle=['-', '--', ':'][repeat-1],label=f'{arm} repeat {repeat}')
        ax.set(xlabel=xlabel,ylabel=ylabel,title=('FAKE ENGINEERING FIXTURE - ' if fake else '')+'Native GEPA V6 selector comparison')
        ax.grid(alpha=.2);ax.legend(fontsize=7)
        fig.savefig(output/(name+'.svg'),metadata={'Creator':'Independent GEPA V6','Date':None})
        fig.savefig(output/(name+'.png'),dpi=160,metadata={'Software':'Independent GEPA V6'})
        plt.close(fig)
    manifest={'identity':'GEPA_V6_FIVE_CURVE_FIGURES','fake_fixture':fake,
        'input_sha256':{f'{a}:{n}':file_hash(run/a/f'repeat_{n}'/'mechanism_events.json') for a,n in curves},
        'files':{p.name:file_hash(p) for p in sorted(output.iterdir()) if p.suffix in ('.svg','.png')},
        'new_model_calls':0}
    write(output/'manifest.json',manifest)
    audit_figures(output)
    return manifest


def audit_figures(output):
    manifest=read(output/'manifest.json')
    if len(manifest['files'])!=10:
        raise ProtocolViolation('FIVE_CURVES_REQUIRED')
    for name,sha in manifest['files'].items():
        path=output/name
        if path.name!=name or file_hash(path)!=sha:
            raise ProtocolViolation('FIGURE_HASH_MISMATCH')
        if path.suffix=='.svg':
            text=path.read_text(encoding='utf-8')
            if SECRET_VALUE.search(text) or WINDOWS_ABSOLUTE.search(text) or POSIX_ABSOLUTE.search(text):
                raise ProtocolViolation('FIGURE_SANITIZATION')
            tree=ET.fromstring(text)
            if any(node.tag.rsplit('}',1)[-1] in ('script','foreignObject','image') for node in tree.iter()):
                raise ProtocolViolation('FIGURE_EXTERNAL_CONTENT')
        elif path.suffix=='.png':
            if not path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
                raise ProtocolViolation('FIGURE_PNG_INVALID')
        else:
            raise ProtocolViolation('FIGURE_FORMAT')
