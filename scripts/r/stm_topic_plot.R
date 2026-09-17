#!/usr/bin/env Rscript

# Render an already-fitted STM model. Analytical fitting/inference belongs upstream.
# Usage: Rscript scripts/r/stm_topic_plot.R model.rds output.pdf [top_n]

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("usage: stm_topic_plot.R model.rds output.pdf [top_n]")
}
if (!requireNamespace("stm", quietly = TRUE)) {
  stop("optional package 'stm' is required")
}

model <- readRDS(args[[1]])
output <- args[[2]]
top_n <- if (length(args) >= 3) as.integer(args[[3]]) else min(20L, model$settings$dim$K)
if (is.na(top_n) || top_n < 1) stop("top_n must be a positive integer")

pdf(output, width = 10, height = 7)
plot(
  model,
  type = "summary",
  n = top_n,
  main = "Precomputed STM topic prevalence"
)
mtext(
  "Topic prevalence is descriptive and is not evidence of hegemony without an explicit operationalization.",
  side = 1,
  line = 4,
  cex = 0.7
)
dev.off()
