"use client";

import { Suspense, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import { PageContainer } from "@/components/layout/page-container";
import { MarketFilters } from "@/components/markets/market-filters";
import { MarketTable } from "@/components/markets/market-table";
import { TableSkeleton } from "@/components/shared/loading-skeleton";

import { useMarkets } from "@/hooks/use-markets";
import { PAGE_TITLES } from "@/lib/constants";

import type { MarketFilters as MarketFiltersType, Platform, MarketStatus } from "@/lib/types";

function parseFiltersFromParams(params: URLSearchParams): MarketFiltersType {
  const filters: MarketFiltersType = {};

  const platform = params.get("platform");
  if (platform && ["polymarket", "kalshi", "manifold", "metaculus"].includes(platform)) {
    filters.platform = platform as Platform;
  }

  const status = params.get("status");
  if (status && ["active", "closed", "resolved"].includes(status)) {
    filters.status = status as MarketStatus;
  }

  const search = params.get("search");
  if (search) {
    filters.search = search;
  }

  return filters;
}

function filtersToParams(filters: MarketFiltersType): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.platform) params.set("platform", filters.platform);
  if (filters.status) params.set("status", filters.status);
  if (filters.search) params.set("search", filters.search);
  return params;
}

function MarketsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = parseFiltersFromParams(searchParams);

  const { data, isLoading } = useMarkets(filters);

  const handleFilterChange = useCallback(
    (newFilters: MarketFiltersType) => {
      const params = filtersToParams(newFilters);
      const qs = params.toString();
      router.push(qs ? `/markets?${qs}` : "/markets");
    },
    [router]
  );

  const tableRows = (data?.markets ?? []).map((market) => ({
    market,
    snapshot: null,
    estimate: null,
    recommendation: null,
  }));

  return (
    <>
      <MarketFilters filters={filters} onFilterChange={handleFilterChange} />
      <MarketTable markets={tableRows} isLoading={isLoading} />
    </>
  );
}

export default function MarketsPage() {
  return (
    <div className="flex h-screen bg-background">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <PageContainer>
          <Header
            title={PAGE_TITLES.markets}
            description="Browse tracked Kalshi sports markets."
          />
          <Suspense fallback={<TableSkeleton rows={10} />}>
            <MarketsContent />
          </Suspense>
        </PageContainer>
      </main>
    </div>
  );
}
