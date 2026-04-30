const LOCAL_API_PORT = '8080';
type RuntimeLocation = Pick<Location, 'hostname' | 'origin' | 'port' | 'protocol'>;

export const getRuntimeApiBase = (configuredApiUrl?: string, locationOverride?: RuntimeLocation) => {
  if (configuredApiUrl) return configuredApiUrl;
  if (!locationOverride && typeof window === 'undefined') return `http://localhost:${LOCAL_API_PORT}`;

  const runtimeLocation = locationOverride ?? window.location;
  const isLocalHost = ['localhost', '127.0.0.1', '::1'].includes(runtimeLocation.hostname);
  if (isLocalHost && runtimeLocation.port !== LOCAL_API_PORT) {
    return `${runtimeLocation.protocol}//${runtimeLocation.hostname}:${LOCAL_API_PORT}`;
  }

  return runtimeLocation.origin;
};
