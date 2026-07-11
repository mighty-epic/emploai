export type LatestAsyncResult<T> =
  | { status: 'completed'; value: T }
  | { status: 'superseded' }
  | { status: 'failed'; error: unknown };

export type LatestRequestGate = {
  begin: () => number;
  isCurrent: (requestId: number) => boolean;
  invalidate: () => void;
};

export function createLatestRequestGate(): LatestRequestGate {
  let generation = 0;
  return {
    begin() {
      generation += 1;
      return generation;
    },
    isCurrent(requestId: number) {
      return requestId === generation;
    },
    invalidate() {
      generation += 1;
    },
  };
}

export type LatestAsyncQueue<T> = {
  schedule: (operation: () => Promise<T>) => Promise<LatestAsyncResult<T>>;
  invalidate: () => void;
};

export function createLatestAsyncQueue<T>(): LatestAsyncQueue<T> {
  let generation = 0;
  let tail: Promise<void> = Promise.resolve();

  return {
    schedule(operation) {
      generation += 1;
      const requestId = generation;
      const task = tail.then(async (): Promise<LatestAsyncResult<T>> => {
        if (requestId !== generation) {
          return { status: 'superseded' };
        }
        try {
          const value = await operation();
          return requestId === generation
            ? { status: 'completed', value }
            : { status: 'superseded' };
        } catch (error) {
          return requestId === generation
            ? { status: 'failed', error }
            : { status: 'superseded' };
        }
      });
      tail = task.then(() => undefined, () => undefined);
      return task;
    },
    invalidate() {
      generation += 1;
    },
  };
}

export type AsyncSingleFlight<T> = {
  run: (operation: () => Promise<T>) => Promise<T>;
  active: () => boolean;
};

export function createAsyncSingleFlight<T>(): AsyncSingleFlight<T> {
  let current: Promise<T> | null = null;
  return {
    run(operation) {
      if (current) {
        return current;
      }
      const task = Promise.resolve().then(operation);
      const settled = task.finally(() => {
        if (current === settled) {
          current = null;
        }
      });
      current = settled;
      return current;
    },
    active() {
      return current !== null;
    },
  };
}
