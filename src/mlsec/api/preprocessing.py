"""
Preprocessing para inferencia — sin escalado.

LightGBM es invariante a escala — los árboles splittean por umbrales,
no por distancias. No se requiere StandardScaler ni ningún otro
preprocesamiento numérico sobre las features.

Este archivo se mantiene por compatibilidad de interface, pero
el escalado ya no se aplica.
"""
