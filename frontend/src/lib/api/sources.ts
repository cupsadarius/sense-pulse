import { api } from './client.js';
import type { AllSources, Source, ConfigData } from '$lib/types/sources.js';

/** Fetch all sources with readings + status */
export async function getSources(customFetch?: typeof fetch): Promise<AllSources> {
	return api<AllSources>('/api/sources', undefined, customFetch);
}

/** Fetch a single source by ID */
export async function getSource(id: string, customFetch?: typeof fetch): Promise<Source> {
	return api<Source>(`/api/sources/${encodeURIComponent(id)}`, undefined, customFetch);
}

/** Fetch all config sections */
export async function getConfig(customFetch?: typeof fetch): Promise<ConfigData> {
	return api<ConfigData>('/api/config', undefined, customFetch);
}
