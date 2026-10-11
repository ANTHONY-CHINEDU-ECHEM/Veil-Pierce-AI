"""Packaging for Veil Pierce AI."""

from pathlib import Path

from setuptools import find_packages, setup

ROOT = Path(__file__).parent

setup(
    name="veilpierce",
    version="1.0.0",
    description="Beneficial ownership opacity and sanctions evasion detection using graph RAG",
    long_description=(ROOT / "README.md").read_text(encoding="utf8") if (ROOT / "README.md").exists() else "",
    long_description_content_type="text/markdown",
    packages=find_packages(include=["veilpierce", "veilpierce.*"]),
    package_data={"veilpierce": ["default.yaml", "knowledge/*.json"]},
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=[
        "numpy>=1.26",
        "pandas>=2.1",
        "scipy>=1.11",
        "scikit_learn>=1.4",
        "networkx>=3.2",
        "matplotlib>=3.8",
        "rapidfuzz>=3.6",
        "joblib>=1.3",
        "pyarrow>=15",
        "pyyaml>=6",
        "fastapi>=0.110",
        "uvicorn>=0.27",
        "pydantic>=2.6",
    ],
    extras_require={
        "dev": ["pytest>=8", "httpx>=0.27"],
        "anthropic": ["anthropic>=0.40"],
        "openai": ["openai>=1.40"],
    },
    entry_points={"console_scripts": ["veilpierce=veilpierce.cli:main"]},
    license="MIT",
)
