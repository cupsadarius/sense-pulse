import type { PageServerLoad } from './$types.js';
import type { AllSources } from '$lib/types/sources.js';

export const load: PageServerLoad = async ({ fetch }) => {
	try {
		const res = await fetch('/api/sources');
		if (res.ok) {
			const sources: AllSources = await res.json();
			return { sources };
		}
		return { sources: {} as AllSources };
	} catch {
		return { sources: {} as AllSources };
	}
};
