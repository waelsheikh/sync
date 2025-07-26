from setuptools import setup, find_packages

# هذا الملف يستخدم لإعداد الحزمة وتثبيتها.
# في هذا المشروع، يتم استخدامه بشكل أساسي لتحديد الحزمة odoorpc
# التي قد تكون جزءًا من المشروع إذا تم تطويرها محليًا.

setup(
    name='odoorpc',
    version='0.1',
    packages=find_packages(),
)