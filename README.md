

Para acceder a PgAdmin con las credenciales por defecto:
http://localhost:5050/
user@domain.com
postgres

Para acceder a GeoServer con las credenciales por defecto:
http://localhost:8081/geoserver/
admin
geoserver

Para cargar uno de los conjuntos de datos de PostgreSQL a GeoServer:
1. Crear un espacio de trabajo Data -> Workspaces
    1.1. Add a new workspace
    1.2. Enter the name as dbsm and Namespace URI as http://localhost:8081/geoserver/dbsm
2. Crear un store
    2.1. Add a new store
    2.2. 
3. Crear una capa
    3.1. Add new layer
    3.2. 
4. Previsualización de capas


Referencias:

https://gdal.org/en/stable/programs/ogr2ogr.html

https://github.com/MODERATE-Project/poc-dbsm-r2023
https://github.com/kartoza/docker-geoserver/blob/develop/docker-compose.yml
https://docs.postgrest.org/en/v12/tutorials/tut0.html

https://www.webgis.dev/posts/setting-up-geoserver-with-docker
