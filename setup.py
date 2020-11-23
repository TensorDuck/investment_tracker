import setuptools


def get_readme():
    with open("README.md", "r") as fh:
        return fh.read()


setuptools.setup(
    name="investment_tracker",  # Replace with your own username
    version="0.0.0",
    author="TensorDuck",
    description="For deploying AWS and GCP functions to track investments",
    long_description=get_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/TensorDuck/investment_tracker",
    packages=["investment_tracker"],
    package_dir={"investment_tracker": "investment_tracker"},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
)
