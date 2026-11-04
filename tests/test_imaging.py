from io import BytesIO
import numpy as np
from PIL import Image
from anatomy_lab.dataset import make_synthetic_demo
from anatomy_lab.geometry import StressExperiment
from anatomy_lab.imaging import display_plane, slice_png


def test_ras_display_convention():
    a=np.zeros((4,5,6),np.int32)
    a[3,4,2]=123
    assert display_plane(a,'axial',2)[0,0]==123
    a[3,2,5]=231
    assert display_plane(a,'coronal',2)[0,0]==231
    a[2,4,5]=198
    assert display_plane(a,'sagittal',2)[0,0]==198


def test_png_slices_and_overlays_render():
    d=make_synthetic_demo()
    e=StressExperiment.from_mask(d.mask('liver'),d.spacing)
    for axis,idx in [('axial',60),('coronal',65),('sagittal',77)]:
        payload=slice_png(d.image,d.mask('liver'),e,axis,idx,1.5,(77,65,60))
        im=Image.open(BytesIO(payload))
        assert im.mode=='RGB'
        assert im.width>50 and im.height>50
