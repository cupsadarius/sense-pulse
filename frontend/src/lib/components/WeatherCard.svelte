<script lang="ts">
	import SourceCard from './SourceCard.svelte';
	import type { Source } from '$lib/types/sources.js';

	interface Props {
		source: Source | undefined;
	}

	let { source }: Props = $props();

	function readingValue<T>(key: string): T | undefined {
		return source?.readings?.[key]?.value as T | undefined;
	}

	let temp = $derived(readingValue<number>('weather_temp'));
	let feelsLike = $derived(readingValue<number>('weather_feels_like'));
	let humidity = $derived(readingValue<number>('weather_humidity'));
	let conditions = $derived(readingValue<string>('weather_conditions'));
	let wind = $derived(readingValue<number>('weather_wind'));
	let windDir = $derived(readingValue<string>('weather_wind_dir'));
	let location = $derived(readingValue<string>('weather_location'));

	interface ForecastDay {
		date: string;
		maxTemp: number;
		minTemp: number;
		avgTemp: number;
		description: string;
	}

	let forecast = $derived.by(() => {
		if (!source?.readings) return [];
		const days: ForecastDay[] = [];
		for (let i = 0; i < 3; i++) {
			const date = readingValue<string>(`forecast_d${i}_date`);
			const maxTemp = readingValue<number>(`forecast_d${i}_max_temp`);
			const minTemp = readingValue<number>(`forecast_d${i}_min_temp`);
			const avgTemp = readingValue<number>(`forecast_d${i}_avg_temp`);
			const description = readingValue<string>(`forecast_d${i}_description`);
			if (date && maxTemp != null && minTemp != null) {
				days.push({
					date,
					maxTemp,
					minTemp,
					avgTemp: avgTemp ?? (maxTemp + minTemp) / 2,
					description: description ?? ''
				});
			}
		}
		return days;
	});
</script>

<SourceCard sourceId="weather" title="Weather" icon="🌤️" {source} expectedInterval={300}>
	<div class="space-y-3">
		{#if location}
			<div class="text-xs text-gray-500">{location}</div>
		{/if}

		{#if conditions}
			<div class="text-sm text-gray-300">{conditions}</div>
		{/if}

		<div class="flex items-end gap-3">
			{#if temp != null}
				<span class="font-mono text-3xl text-gray-100">{temp.toFixed(0)}&deg;</span>
			{/if}
			{#if feelsLike != null}
				<span class="mb-1 text-sm text-gray-400">Feels {feelsLike.toFixed(0)}&deg;</span>
			{/if}
		</div>

		<div class="grid grid-cols-2 gap-2 text-sm">
			{#if wind != null}
				<div class="flex items-baseline justify-between">
					<span class="text-gray-400">Wind</span>
					<span class="font-mono text-gray-200">{wind} {windDir ?? ''}</span>
				</div>
			{/if}
			{#if humidity != null}
				<div class="flex items-baseline justify-between">
					<span class="text-gray-400">Humidity</span>
					<span class="font-mono text-gray-200">{humidity}%</span>
				</div>
			{/if}
		</div>

		{#if forecast.length > 0}
			<div class="mt-2 border-t border-pulse-border pt-2">
				<div class="grid grid-cols-3 gap-2">
					{#each forecast as day (day.date)}
						<div class="rounded bg-pulse-bg p-2 text-center">
							<div class="text-xs text-gray-500">
								{new Date(day.date + 'T00:00:00').toLocaleDateString('en', { weekday: 'short' })}
							</div>
							<div class="font-mono text-sm text-gray-200">
								{day.maxTemp.toFixed(0)}&deg;
							</div>
							<div class="font-mono text-xs text-gray-500">
								{day.minTemp.toFixed(0)}&deg;
							</div>
							{#if day.description}
								<div class="mt-0.5 truncate text-xs text-gray-400" title={day.description}>
									{day.description}
								</div>
							{/if}
						</div>
					{/each}
				</div>
			</div>
		{/if}
	</div>
</SourceCard>
