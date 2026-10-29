"""Embedded time playback and plots for the elastic plate drop-test study."""
import html
import json
from pathlib import Path
import numpy as np


def write_impact_report(directory,p,history,q,modes,summary):
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    directory=Path(directory)
    fig=Figure(figsize=(11,7),layout='constrained');FigureCanvasAgg(fig)
    ax=fig.subplots(2,2);time=history[:,0]*1000
    ax[0,0].plot(time,history[:,3]);ax[0,0].set(xlabel='Time (ms)',ylabel='Contact force (N)')
    ax[0,1].plot(time,history[:,1]*1000,label='Drop weight');ax[0,1].plot(time,history[:,2]*1000,label='Plate patch');ax[0,1].set(xlabel='Time (ms)',ylabel='Downward displacement (mm)');ax[0,1].legend()
    for i,label in [(4,'Kinetic'),(5,'Plate elastic'),(6,'Contact elastic'),(7,'Dissipated'),(8,'Gravity potential')]:ax[1,0].plot(time,history[:,i],label=label)
    ax[1,0].set(xlabel='Time (ms)',ylabel='Energy (J)');ax[1,0].legend(fontsize=8)
    ax[1,1].plot(time,history[:,9]*100);ax[1,1].set(xlabel='Time (ms)',ylabel='Energy balance error (%)')
    for axis in ax.flat:axis.grid(alpha=.25)
    fig.savefig(directory/'plot.png',dpi=130)
    a,b=p['impact_length_m'],p['impact_width_m'];x=np.linspace(0,a,31);y=np.linspace(0,b,23)
    xx,yy=np.meshgrid(x,y);shape=np.sin(np.pi*xx.ravel()[:,None]*modes[:,0]/a)*np.sin(np.pi*yy.ravel()[:,None]*modes[:,1]/b)
    indices=np.unique(np.linspace(0,len(history)-1,min(161,len(history)),dtype=int))
    data={'x':x.tolist(),'y':y.tolist(),'frames':(q[indices]@shape.T).tolist(),'time':history[indices,0].tolist(),
          'weight':history[indices,1].tolist(),'patchDisplacement':history[indices,2].tolist(),'force':history[indices,3].tolist(),'patch':p['impact_patch_m'],'thickness':p['impact_thickness_m']}
    template=Path(__file__).with_name('impact_viewer.html').read_text(encoding='utf-8')
    rows=''.join('<tr><td>'+html.escape(k)+'</td><td>'+html.escape(str(v))+'</td></tr>' for k,v in summary.items() if k not in {'limitations','accuracy_note','nodes','tetrahedra'})
    inputs=''.join('<tr><td>'+html.escape(k)+'</td><td>'+html.escape(str(v))+'</td></tr>' for k,v in p.items() if k.startswith('impact_'))
    document=template.replace('__INPUT_ROWS__',inputs).replace('__IMPACT_DATA__',json.dumps(data,allow_nan=False).replace('<','\\u003c')).replace('__SUMMARY_ROWS__',rows).replace('__LIMITS__',html.escape(summary['limitations'])).replace('__ACCURACY__',html.escape(summary['accuracy_note']))
    (directory/'report.html').write_text(document,encoding='utf-8')
