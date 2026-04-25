import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/**
 * Global synthesis session store.
 *
 * Persisted fields (localStorage key: 'synthesis-store'):
 *   targetSmiles, optimizeFor, planningHistory
 *
 * Ephemeral (cleared on page refresh):
 *   plannedRoutes, selectedRouteIndex, retrosynthesis*, isPlanning, lastError
 */
const useSynthesisStore = create(
  persist(
    (set, get) => ({

      // ── Current planning session ──────────────────────────────
      targetSmiles:       '',
      optimizeFor:        'balanced',
      plannedRoutes:      [],   // full response from /api/synthesis/plan
      selectedRouteIndex: 0,
      planningHistory:    [],   // last 10 sessions { target, routes, timestamp }

      // ── Retrosynthesis ────────────────────────────────────────
      retrosynthesisTarget: '',
      retrosynthesisRoutes: [],

      // ── Last ML predictions (for cross-page display) ──────────
      lastYieldPrediction: null,
      lastConditions:      null,

      // ── UI state ─────────────────────────────────────────────
      isPlanning: false,
      lastError:  null,

      // ── Actions ───────────────────────────────────────────────

      setTargetSmiles: (smiles) => set({ targetSmiles: smiles }),
      setOptimizeFor:  (mode)   => set({ optimizeFor: mode }),

      setPlannedRoutes: (routes) => {
        const target = get().targetSmiles;
        set({
          plannedRoutes:      routes,
          selectedRouteIndex: 0,
          planningHistory: [
            {
              target,
              routes,
              timestamp:   new Date().toISOString(),
              routeCount:  routes.length,
              bestYield:   routes[0]?.overall_yield_percent ?? null,
            },
            ...get().planningHistory.slice(0, 9),   // keep last 10
          ],
        });
      },

      setSelectedRoute: (index) => set({ selectedRouteIndex: index }),

      getSelectedRoute: () => {
        const { plannedRoutes, selectedRouteIndex } = get();
        return plannedRoutes[selectedRouteIndex] ?? null;
      },

      setRetrosynthesisRoutes: (target, routes) => set({
        retrosynthesisTarget: target,
        retrosynthesisRoutes: routes,
      }),

      setLastYieldPrediction: (pred)  => set({ lastYieldPrediction: pred }),
      setLastConditions:      (cond)  => set({ lastConditions: cond }),

      setPlanning: (bool)  => set({ isPlanning: bool }),
      setError:    (error) => set({ lastError: error }),

      clearSession: () => set({
        targetSmiles:        '',
        plannedRoutes:       [],
        selectedRouteIndex:  0,
        retrosynthesisTarget:'',
        retrosynthesisRoutes:[],
        lastYieldPrediction: null,
        lastConditions:      null,
        lastError:           null,
      }),

      clearHistory: () => set({ planningHistory: [] }),
    }),
    {
      name: 'synthesis-store',
      // Only persist the fields that survive page refresh usefully
      partialize: (state) => ({
        targetSmiles:    state.targetSmiles,
        optimizeFor:     state.optimizeFor,
        planningHistory: state.planningHistory,
      }),
    }
  )
);

export default useSynthesisStore;
