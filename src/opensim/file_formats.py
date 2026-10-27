"""Shared file extensions without loading native meshing libraries."""

CAD_SUFFIXES = {".step", ".stp", ".iges", ".igs", ".brep"}
MESH_SUFFIXES = {".stl", ".obj", ".3mf"}
SUPPORTED_SUFFIXES = CAD_SUFFIXES | MESH_SUFFIXES
