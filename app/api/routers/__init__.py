"""Router registrations."""

from .comparative import router as comparative
from .expression import router as expression
from .gene import router as gene
from .gene import genehub_router as genehub
from .gene import pfam_router as pfam
from .gene import interval_router as interval
from .literature import router as literature
from .coexpression import coexpression_router as coexpression
from .ppi import ppi_router as ppi
from .sequence import router as sequence
from .blast import router as blast
from .primer_server import router as primer_server
from .triticeae import router as triticeae
