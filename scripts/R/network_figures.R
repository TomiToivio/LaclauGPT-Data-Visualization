#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3) stop("usage: network_figures.R NODES.csv EDGES.csv OUTPUT.png")

suppressPackageStartupMessages({
  library(igraph)
  library(ggraph)
  library(ggplot2)
})
nodes <- read.csv(args[[1]], stringsAsFactors = FALSE)
edges <- read.csv(args[[2]], stringsAsFactors = FALSE)
if (!("id" %in% names(nodes))) stop("nodes CSV requires id")
if (!all(c("source", "target") %in% names(edges))) stop("edges CSV requires source and target")

graph <- graph_from_data_frame(edges, directed = TRUE, vertices = nodes)
plot <- ggraph(graph, layout = "stress") +
  geom_edge_link(alpha = 0.25) +
  geom_node_point() +
  geom_node_text(aes(label = name), repel = TRUE, size = 2.6) +
  labs(
    title = "Descriptive network",
    subtitle = "Layout proximity and degree are descriptive, not equivalence or nodal status."
  ) +
  theme_void()
ggsave(args[[3]], plot = plot, width = 9, height = 7, dpi = 160)
