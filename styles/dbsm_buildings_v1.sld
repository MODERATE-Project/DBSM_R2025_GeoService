<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0"
  xmlns="http://www.opengis.net/sld"
  xmlns:ogc="http://www.opengis.net/ogc"
  xmlns:xlink="http://www.w3.org/1999/xlink"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.opengis.net/sld StyledLayerDescriptor.xsd">
  <NamedLayer>
    <Name>dbsm_buildings_v1</Name>
    <UserStyle>
      <Title>DBSM Buildings v1 (R2023)</Title>
      <Abstract>Building footprints from DBSM R2023. Flat style — no height attribute available in this version.</Abstract>
      <FeatureTypeStyle>
        <Rule>
          <Name>building</Name>
          <Title>Building</Title>
          <PolygonSymbolizer>
            <Fill>
              <CssParameter name="fill">#FFCC88</CssParameter>
              <CssParameter name="fill-opacity">0.8</CssParameter>
            </Fill>
            <Stroke>
              <CssParameter name="stroke">#CC8844</CssParameter>
              <CssParameter name="stroke-width">0.4</CssParameter>
            </Stroke>
          </PolygonSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
