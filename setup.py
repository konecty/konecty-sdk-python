from setuptools import find_packages, setup

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="konecty_sdk_python",
    version="1.0.5",
    packages=find_packages(),
    package_dir={"": "KonectySdkPython"},
    long_description=long_description,
    long_description_content_type="text/markdown",
    install_requires=[
        "aiohttp>=3.11.11",
        "asyncio>=3.4.3",
        "black>=24.10.0",
        "email-validator>=2.2.0",
        "inquirer>=3.4.0",
        "pymongo>=4.10.1",
        "requests>=2.32.3",
        "rich>=13.9.4",
        "typing-extensions>=4.12.2",
        "pydantic>=2.11.4",
    ],
    entry_points={
        "console_scripts": [
            "konecty-cli=cli.main:main",
        ],
    },
)
