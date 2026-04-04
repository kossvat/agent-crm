from setuptools import setup

setup(
    name="agentcrm",
    version="0.1.0",
    description="Universal CLI for AI Agent CRM — works with any agent framework",
    py_modules=["agentcrm"],
    install_requires=["requests>=2.28"],
    entry_points={
        "console_scripts": [
            "agentcrm=agentcrm:main",
        ],
    },
    python_requires=">=3.9",
)
