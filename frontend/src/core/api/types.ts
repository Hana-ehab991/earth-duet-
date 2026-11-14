/** Shared API types — mirror backend/app/schemas/datasets.py. Feature-agnostic. */
export type RecordType = 'observation' | 'reanalysis' | 'model_historical' | 'projection' | 'synthetic_demo'

export interface Source { name: string; url: string; product: string; parameter: string; citation_note?: string | null; extra?: Record<string, unknown> }
export interface Geometry { type: 'point' | 'bbox' | 'polygon'; latitude?: number | null; longitude?: number | null; support_bbox?: number[] | null; spatial_support: string }
export interface Processing { method: string; missing_value_handling?: string | null; retrieved_at?: string | null; request?: string | null; extra?: Record<string, unknown> }
export interface Baseline { period: [number, number]; mean?: number | null; description: string }

export interface ObservedRecord { year: number; value: number | null; complete: boolean; n_months: number; reason?: string | null }
export interface ObservedDataset {
  dataset_id: string; location_id: string; variable_id: string; record_type: RecordType; is_demo: boolean; unit: string
  source: Source; geometry: Geometry; processing: Processing; baseline: Baseline; coverage: Record<string, unknown>
  records: ObservedRecord[]
}
export interface TimeseriesResponse { dataset: ObservedDataset; latest_complete_year: number | null; first_year: number | null; available_years: number[] }

export interface ModelRef { id: string; variant?: string | null; note?: string | null }
export interface WindowDef { target_year: number; start_year: number; end_year: number; clipped: boolean }
export interface ProjectionRecord { scenario: string; target_year: number; model: string; value: number; baseline: number; anomaly: number }
export interface EnsembleStat {
  scenario: string; target_year: number; n_models: number; mean: number; min: number; max: number; std: number
  anomaly_mean: number; anomaly_min: number; anomaly_max: number
}
export interface ProjectionDataset {
  dataset_id: string; location_id: string; variable_id: string; record_type: RecordType; is_demo: boolean; unit: string
  source: Source; geometry: Geometry; processing: Processing; baseline: Baseline; models: ModelRef[]; scenarios: string[]
  windows: WindowDef[]; records: ProjectionRecord[]; ensemble: EnsembleStat[]; uncertainty_note: string
}
export interface ClimateResponse { dataset: ProjectionDataset; disclaimer: string }

export interface LocationInfo {
  id: string; name: string; country: string | null; latitude: number; longitude: number; default_zoom_meters: number
  primary_variable: string; status: string; analysis_geometry: Record<string, unknown>
  dataset_status: 'configured' | 'demo_only' | 'not_configured' | 'data_not_fetched'; dataset_message: string
}
export interface VariableInfo {
  id: string; name: string; short_name: string; unit: string | null; kind: string
  reference_range: { min: number; max: number; rationale: string } | null
  anomaly_range: { min: number; max: number } | null
}
export interface ScenarioInfo { id: string; label: string; description: string }
export interface ScenariosResponse { scenarios: ScenarioInfo[]; disclaimer: string }

export interface ImageryLayerMeta {
  id: string; title: string; gibs_layer: string; max_zoom: number; tile_url_template: string; documented_start_date: string
  representative_date_rationale: string; attribution: string; docs_url: string; worldview_url: string
  verified_in_build_environment: boolean; verification_note: string
}
export interface ImageryAvailability { available: boolean; date: string | null; reason: string | null }
export interface ImageryResponse { layers: ImageryLayerMeta[]; resolution_note: string; year?: number; availability?: Record<string, ImageryAvailability> }
export interface HealthResponse { status: string; demo_mode: boolean; locations: Record<string, string>; data_dir?: string; processed_dir?: string; processed_files?: Record<string, { exists: boolean; bytes: number | null }> }
