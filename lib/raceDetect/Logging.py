import logging

logging.basicConfig(level=logging.DEBUG, datefmt="%Y-%m-%d-%H:%M:%S", format='%(asctime)s-%(levelname)s-%(message)s')
logger=logging.getLogger(__name__)