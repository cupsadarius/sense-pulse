/** Base API fetch wrapper with configurable base URL and auth */

export class ApiError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
		this.name = 'ApiError';
	}
}

function getBaseUrl(): string {
	// In SSR context, use internal gateway URL; in browser, use relative paths (proxied by vite/traefik)
	if (typeof window === 'undefined') {
		return 'http://localhost:8080';
	}
	return '';
}

let authCredentials: string | null = null;

/** Set Basic Auth credentials for API calls */
export function setAuth(username: string, password: string): void {
	authCredentials = btoa(`${username}:${password}`);
}

/** Clear stored auth credentials */
export function clearAuth(): void {
	authCredentials = null;
}

/** Type-safe fetch wrapper */
export async function api<T>(
	path: string,
	init?: RequestInit,
	customFetch?: typeof fetch
): Promise<T> {
	const baseUrl = getBaseUrl();
	const url = `${baseUrl}${path}`;

	const headers = new Headers(init?.headers);
	if (!headers.has('Content-Type') && init?.body) {
		headers.set('Content-Type', 'application/json');
	}
	if (authCredentials) {
		headers.set('Authorization', `Basic ${authCredentials}`);
	}

	const fetchFn = customFetch ?? fetch;
	const res = await fetchFn(url, { ...init, headers });

	if (!res.ok) {
		const text = await res.text().catch(() => res.statusText);
		throw new ApiError(res.status, text);
	}

	return res.json() as Promise<T>;
}
