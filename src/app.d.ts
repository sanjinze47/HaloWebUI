// See https://kit.svelte.dev/docs/types#app
// for information about these interfaces
declare global {
	const APP_VERSION: string | undefined;
	const APP_BUILD_HASH: string | undefined;
	const APP_ENABLE_PYODIDE: boolean;
	const APP_PYODIDE_INDEX_URL: string;

	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		// interface Platform {}
	}
}

export {};
