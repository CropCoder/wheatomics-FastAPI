"""Router registrations."""

from .comparative import router as comparative
from .expression import router as expression
from .gene import router as gene
from .gene import genehub_router as genehub
from .gene import pfam_router as pfam
from .gene import interval_router as interval
from .coexpression import coexpression_router as coexpression
from .ppi import ppi_router as ppi
from .sequence import router as sequence
from .sequence import blast_extra_router as blast_extra
from .blast import router as blast
from .triticeae import router as triticeae
