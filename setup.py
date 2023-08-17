from setuptools import setup, find_packages

# Read the content of README.md
with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="SEC-Client",
    version="0.1",
    packages=find_packages(),
    py_modules=["stripe_models"],
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
    install_requires=[
        "requests",
        "bs4",
        "faker",
        "pyrate-limiter",
        "pandas",
        "numpy"
    ]
)





