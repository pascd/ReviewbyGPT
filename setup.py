"""Packaging metadata for the ``reviewbygpt`` distribution.

See ``pyproject.toml`` for the build backend and pytest configuration.
"""

from pathlib import Path

from setuptools import find_packages, setup

_ROOT = Path(__file__).parent
long_description = (_ROOT / "README.md").read_text(encoding="utf-8")

setup(
    name="reviewbygpt",
    version="0.1.0",
    description=(
        "Automate literature-review quality assessment and data extraction "
        "from PDFs into Excel, using any OpenAI-compatible LLM backend."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Pedro Dias",
    author_email="pedro.afonso.cardoso.dias@gmail.com",
    url="https://github.com/pascd/ReviewbyGPT",
    license="MIT",
    packages=find_packages(exclude=["tests", "tests.*"]),
    python_requires=">=3.9",
    install_requires=[
        "PyPDF2",
        "PyYAML",
        "requests",
        "openpyxl",
    ],
    extras_require={
        "test": ["pytest>=7.0"],
    },
    entry_points={
        "console_scripts": [
            "reviewbygpt=reviewbygpt.scripts.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering",
        "Topic :: Text Processing :: General",
    ],
)
