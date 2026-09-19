#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2) stop("usage: timeline_figures.R TIMELINE.csv OUTPUT.png")

suppressPackageStartupMessages(library(ggplot2))
timeline <- read.csv(args[[1]], stringsAsFactors = FALSE)
if (!all(c("period", "documents") %in% names(timeline))) {
  stop("timeline CSV requires period and documents columns")
}
timeline$period <- as.POSIXct(timeline$period, tz = "UTC")
plot <- ggplot(timeline, aes(x = period, y = documents)) +
  geom_line() +
  geom_point() +
  labs(
    title = "Document timeline",
    subtitle = "Descriptive counts only; frequency does not establish hegemony.",
    x = NULL,
    y = "Documents"
  ) +
  theme_minimal()
ggsave(args[[2]], plot = plot, width = 9, height = 5, dpi = 160)
