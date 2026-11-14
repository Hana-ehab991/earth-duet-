import {
  Cartesian3, Color, ConstantPositionProperty, ConstantProperty, Entity, HeightReference, ImageryLayer, Ion, LabelStyle, Math as CMath, NearFarScalar,
  Rectangle, ScreenSpaceEventHandler, ScreenSpaceEventType, TileMapServiceImageryProvider, UrlTemplateImageryProvider,
  VerticalOrigin, Viewer, buildModuleUrl, defined, Cartesian2, LabelGraphics,
} from 'cesium'
import 'cesium/Build/Cesium/Widgets/widgets.css'

/** `color` (CSS), `size` (px) and `labelText` are optional per-marker styling; without them the original cyan/grey look is used. */
export interface GlobeMarker { id: string; name: string; latitude: number; longitude: number; selected?: boolean; color?: string; size?: number; labelText?: string }
export interface TileOverlaySpec { id: string; url: string; maxLevel: number; credit: string; alpha?: number }
export interface SupportRect { bbox: [number, number, number, number]; color: string; label: string }
export type OverlayStatus = { state: 'loading' | 'ok' | 'partial' | 'failed'; errors: number }

/**
 * Feature-agnostic CesiumJS wrapper. Knows nothing about Time Travel, temperature or Cairo.
 * Features push state in (markers, tile overlay, a colored support rectangle) and receive events out.
 * Base map is Cesium's bundled Natural Earth II raster (no token needed) and is always labelled as a base map.
 */
export class GlobeEngine {
  readonly viewer: Viewer
  private overlay: ImageryLayer | null = null
  private overlayToken = 0
  private markerEntities = new Map<string, Entity>()
  private rect: Entity | null = null
  private handler: ScreenSpaceEventHandler
  private disposed = false
  onCoordinates?: (c: { lat: number; lon: number } | null) => void
  onMarkerClick?: (id: string) => void
  /** Opt-in: fired for a click on the globe surface (not on a marker). Off unless setGlobeClickEnabled(true). `null` = click missed the globe. */
  onGlobeClick?: (c: { lat: number; lon: number } | null) => void
  private globeClickEnabled = false
  private markerPos = new Map<string, string>()

  constructor(container: HTMLElement, ionToken?: string) {
    if (ionToken) Ion.defaultAccessToken = ionToken
    this.viewer = new Viewer(container, {
      baseLayer: ImageryLayer.fromProviderAsync(TileMapServiceImageryProvider.fromUrl(buildModuleUrl('Assets/Textures/NaturalEarthII'))),
      baseLayerPicker: false, geocoder: false, homeButton: false, sceneModePicker: false, navigationHelpButton: false,
      animation: false, timeline: false, fullscreenButton: false, infoBox: false, selectionIndicator: false,
      requestRenderMode: false,
    })
    const scene = this.viewer.scene
    scene.globe.enableLighting = false
    scene.globe.showGroundAtmosphere = true
    if (scene.skyAtmosphere) scene.skyAtmosphere.show = true
    scene.backgroundColor = Color.fromCssColorString('#050b1d')
    scene.screenSpaceCameraController.minimumZoomDistance = 20000
    scene.screenSpaceCameraController.maximumZoomDistance = 40_000_000

    this.handler = new ScreenSpaceEventHandler(this.viewer.scene.canvas)
    this.handler.setInputAction((m: { endPosition: Cartesian2 }) => {
      const c = this.viewer.camera.pickEllipsoid(m.endPosition, scene.globe.ellipsoid)
      if (!c) return this.onCoordinates?.(null)
      const g = scene.globe.ellipsoid.cartesianToCartographic(c)
      this.onCoordinates?.({ lat: CMath.toDegrees(g.latitude), lon: CMath.toDegrees(g.longitude) })
    }, ScreenSpaceEventType.MOUSE_MOVE)
    this.handler.setInputAction((m: { position: Cartesian2 }) => {
      const p = scene.pick(m.position)
      if (defined(p) && p.id instanceof Entity && this.markerEntities.has(p.id.id)) { this.onMarkerClick?.(p.id.id); return }
      if (!this.globeClickEnabled) return
      const c = this.viewer.camera.pickEllipsoid(m.position, scene.globe.ellipsoid)
      if (!c) return this.onGlobeClick?.(null)
      const g = scene.globe.ellipsoid.cartesianToCartographic(c)
      this.onGlobeClick?.({ lat: CMath.toDegrees(g.latitude), lon: CMath.toDegrees(g.longitude) })
    }, ScreenSpaceEventType.LEFT_CLICK)
  }

  /** Enable/disable globe-surface click reporting. Enabling also removes Cesium's built-in double-click entity tracking so a fast second click cannot lock the camera onto a marker. */
  setGlobeClickEnabled(on: boolean) {
    if (on === this.globeClickEnabled) return
    this.globeClickEnabled = on
    if (on) this.viewer.screenSpaceEventHandler.removeInputAction(ScreenSpaceEventType.LEFT_DOUBLE_CLICK)
  }

  flyTo(lat: number, lon: number, heightMeters: number, reducedMotion: boolean) {
    this.viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(lon, lat, heightMeters),
      duration: reducedMotion ? 0 : 2.2,
    })
  }

  setMarkers(markers: GlobeMarker[]) {
    const keep = new Set(markers.map((m) => m.id))
    for (const [id, e] of this.markerEntities) if (!keep.has(id)) { this.viewer.entities.remove(e); this.markerEntities.delete(id); this.markerPos.delete(id) }
    for (const m of markers) {
      const color = m.color ? Color.fromCssColorString(m.color) : m.selected ? Color.fromCssColorString('#22d3ee') : Color.fromCssColorString('#94a3b8')
      const size = m.size ?? 11
      const text = m.labelText ?? m.name
      let e = this.markerEntities.get(m.id)
      if (!e) {
        e = this.viewer.entities.add(new Entity({
          id: m.id, name: m.name,
          position: Cartesian3.fromDegrees(m.longitude, m.latitude),
          point: { pixelSize: size, color, outlineColor: Color.fromCssColorString('#04122b'), outlineWidth: 2, heightReference: HeightReference.CLAMP_TO_GROUND, disableDepthTestDistance: Number.POSITIVE_INFINITY },
          label: new LabelGraphics({ text, font: '600 13px system-ui, sans-serif', fillColor: Color.WHITE, outlineColor: Color.fromCssColorString('#04122b'), outlineWidth: 3, style: LabelStyle.FILL_AND_OUTLINE, verticalOrigin: VerticalOrigin.BOTTOM, pixelOffset: new Cartesian2(0, -14), translucencyByDistance: new NearFarScalar(1e6, 1, 3e7, 0.5), disableDepthTestDistance: Number.POSITIVE_INFINITY }),
        }))
        this.markerEntities.set(m.id, e)
        this.markerPos.set(m.id, `${m.latitude},${m.longitude}`)
      } else {
        if (e.point) { e.point.color = new ConstantProperty(color); e.point.pixelSize = new ConstantProperty(size) }
        const pos = `${m.latitude},${m.longitude}`
        if (this.markerPos.get(m.id) !== pos) {
          e.position = new ConstantPositionProperty(Cartesian3.fromDegrees(m.longitude, m.latitude))
          this.markerPos.set(m.id, pos)
        }
        if (e.label) e.label.text = new ConstantProperty(text)
      }
    }
  }

  /** Colored rectangle showing the nominal native-grid cell of a dataset (honest spatial support). */
  setSupportRect(spec: SupportRect | null, fillAlpha = 0.6) {
    if (this.rect) { this.viewer.entities.remove(this.rect); this.rect = null }
    if (!spec) return
    const c = Color.fromCssColorString(spec.color)
    this.rect = this.viewer.entities.add({
      name: spec.label,
      rectangle: { coordinates: Rectangle.fromDegrees(...spec.bbox), material: c.withAlpha(fillAlpha), outline: true, outlineColor: Color.WHITE, outlineWidth: 2, height: 0 },
    })
  }

  /** Replace the tile overlay (e.g. GIBS imagery). Passing null removes it. Stale-safe via token. */
  setTileOverlay(spec: TileOverlaySpec | null, onStatus: (s: OverlayStatus) => void, fade: boolean) {
    const token = ++this.overlayToken
    if (this.overlay) { this.viewer.imageryLayers.remove(this.overlay, true); this.overlay = null }
    if (!spec) return
    const provider = new UrlTemplateImageryProvider({ url: spec.url, maximumLevel: spec.maxLevel, credit: spec.credit })
    const layer = new ImageryLayer(provider, { alpha: fade ? 0 : (spec.alpha ?? 1) })
    this.viewer.imageryLayers.add(layer)
    this.overlay = layer
    let errors = 0, ok = 0
    onStatus({ state: 'loading', errors: 0 })
    provider.errorEvent.addEventListener((err) => {
      if (token !== this.overlayToken) return
      err.retry = false
      errors++
      onStatus({ state: ok > 0 ? 'partial' : 'failed', errors })
    })
    // Treat successful tile draws as proof imagery loaded.
    const tilesCheck = setInterval(() => {
      if (token !== this.overlayToken || this.disposed) return clearInterval(tilesCheck)
      if (this.viewer.scene.globe.tilesLoaded && errors === 0) { ok++; onStatus({ state: 'ok', errors: 0 }); clearInterval(tilesCheck) }
      else if (this.viewer.scene.globe.tilesLoaded && errors > 0) { clearInterval(tilesCheck) }
    }, 600)
    if (fade) {
      const t0 = performance.now()
      const step = () => {
        if (token !== this.overlayToken || this.disposed) return
        const a = Math.min(1, (performance.now() - t0) / 700)
        layer.alpha = a * (spec.alpha ?? 1)
        if (a < 1) requestAnimationFrame(step)
      }
      requestAnimationFrame(step)
    }
  }

  dispose() {
    this.disposed = true
    this.overlayToken++
    this.handler.destroy()
    if (!this.viewer.isDestroyed()) this.viewer.destroy()
  }
}
