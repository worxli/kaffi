from setuptools import setup, find_packages
setup(
      name = "Kaffi",
      version = "1.0.0",
      packages = find_packages(),
      install_requires = ['SQLAlchemy', 'serial']
)
