<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis maxScale="0" version="3.18.0-Zürich" minScale="1e+08" hasScaleBasedVisibilityFlag="0" styleCategories="AllStyleCategories">
  <flags>
    <Identifiable>1</Identifiable>
    <Removable>1</Removable>
    <Searchable>0</Searchable>
    <Private>0</Private>
  </flags>
  <temporal mode="0" enabled="0" fetchMode="0">
    <fixedRange>
      <start></start>
      <end></end>
    </fixedRange>
  </temporal>
  <customproperties>
    <property value="false" key="WMSBackgroundLayer"/>
    <property value="false" key="WMSPublishDataSourceUrl"/>
    <property value="0" key="embeddedWidgets/count"/>
    <property value="Value" key="identify/format"/>
  </customproperties>
  <pipe>
    <provider>
      <resampling enabled="false" maxOversampling="2" zoomedOutResamplingMethod="bilinear" zoomedInResamplingMethod="nearestNeighbour"/>
    </provider>
    <rasterrenderer opacity="1" band="1" nodataColor="" type="paletted" alphaBand="-1">
      <rasterTransparency/>
      <minMaxOrigin>
        <limits>None</limits>
        <extent>WholeRaster</extent>
        <statAccuracy>Estimated</statAccuracy>
        <cumulativeCutLower>0.02</cumulativeCutLower>
        <cumulativeCutUpper>0.98</cumulativeCutUpper>
        <stdDevFactor>2</stdDevFactor>
      </minMaxOrigin>
      <colorPalette>
        <paletteEntry alpha="255" value="3" label="3 Åkermark" color="#ffffbc"/>
        <paletteEntry alpha="255" value="21" label="21 Öppen våtmark på myr" color="#884464"/>
        <paletteEntry alpha="255" value="22" label="22 Öppen våtmark ej på myr" color="#6d4286"/>
        <paletteEntry alpha="255" value="41" label="41 Öppen mark utan vegetation" color="#e0e0e0"/>
        <paletteEntry alpha="255" value="51" label="51 Exploaterad mark, byggnad" color="#581313"/>
        <paletteEntry alpha="255" value="52" label="52 Exploaterad mark, ej byggnad/väg" color="#e24549"/>
        <paletteEntry alpha="255" value="53" label="53 Exploaterad mark, väg/järnväg" color="#161616"/>
        <paletteEntry alpha="255" value="54" label="54 Exploaterad mark, torvtäkt" color="#8c1964"/>
        <paletteEntry alpha="255" value="61" label="61 Sjö och vattendrag" color="#6699cc"/>
        <paletteEntry alpha="255" value="62" label="62 Hav" color="#89ccf9"/>
        <paletteEntry alpha="255" value="101" label="101 Tallskog" color="#6d8b05"/>
        <paletteEntry alpha="255" value="102" label="102 Granskog" color="#2c5f00"/>
        <paletteEntry alpha="255" value="103" label="103 Barrblandskog" color="#4e6f00"/>
        <paletteEntry alpha="255" value="104" label="104 Lövblandad barrskog" color="#38a800"/>
        <paletteEntry alpha="255" value="105" label="105 Triviallövskog" color="#4be600"/>
        <paletteEntry alpha="255" value="106" label="106 Ädellövskog" color="#aaff00"/>
        <paletteEntry alpha="255" value="107" label="107 Triviallövskog med ädellövinslag" color="#96e600"/>
        <paletteEntry alpha="255" value="108" label="108 Temporärt ej skog" color="#cdcd66"/>
        <paletteEntry alpha="255" value="200" label="200 Öppen våtmark" color="#c29cd5"/>
        <paletteEntry alpha="255" value="421" label="421 Buskdominerad mark" color="#ccd69e"/>
        <paletteEntry alpha="255" value="422" label="422 Risdominerad mark" color="#d6c29e"/>
        <paletteEntry alpha="255" value="423" label="423 Gräsdominerad mark" color="#ffebae"/>
      </colorPalette>
      <colorramp type="randomcolors" name="[source]">
        <Option/>
      </colorramp>
    </rasterrenderer>
    <brightnesscontrast gamma="1" brightness="0" contrast="0"/>
    <huesaturation colorizeGreen="128" grayscaleMode="0" colorizeRed="255" colorizeBlue="128" colorizeStrength="100" saturation="0" colorizeOn="0"/>
    <rasterresampler maxOversampling="2" zoomedOutResampler="bilinear"/>
    <resamplingStage>resamplingFilter</resamplingStage>
  </pipe>
  <blendMode>0</blendMode>
</qgis>
