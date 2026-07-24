import { useCallback, useEffect, useRef, useState } from 'react';

export const FLEET_AUTO_COLLAPSE_MS = 30 * 60 * 1000;

export function useFleetAutoDisclosure({
  scopeKey,
  activitySignature,
  hasLiveActivity = false,
}: {
  scopeKey: string;
  activitySignature: string;
  hasLiveActivity?: boolean;
}) {
  const [expanded, setExpanded] = useState(hasLiveActivity);
  const previousSignatureRef = useRef(activitySignature);
  const lastActivityAtRef = useRef<number | null>(hasLiveActivity ? Date.now() : null);

  useEffect(() => {
    previousSignatureRef.current = activitySignature;
    lastActivityAtRef.current = hasLiveActivity ? Date.now() : null;
    setExpanded(hasLiveActivity);
  }, [scopeKey]);

  useEffect(() => {
    if (activitySignature === previousSignatureRef.current) return;
    previousSignatureRef.current = activitySignature;
    lastActivityAtRef.current = Date.now();
    setExpanded(true);
  }, [activitySignature]);

  useEffect(() => {
    if (!expanded || hasLiveActivity) return undefined;
    const lastActivityAt = lastActivityAtRef.current || Date.now();
    const remaining = Math.max(0, FLEET_AUTO_COLLAPSE_MS - (Date.now() - lastActivityAt));
    const timer = setTimeout(() => setExpanded(false), remaining);
    return () => clearTimeout(timer);
  }, [expanded, hasLiveActivity, activitySignature]);

  const toggle = useCallback(() => {
    lastActivityAtRef.current = Date.now();
    setExpanded((current) => !current);
  }, []);

  return { expanded, setExpanded, toggle };
}
