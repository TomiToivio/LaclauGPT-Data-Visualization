args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3) {
  stop("Usage: Rscript dna_network_plot.R nodes.csv edges.csv output.pdf")
}

nodes_path <- args[[1]]
edges_path <- args[[2]]
out_path <- args[[3]]

suppressPackageStartupMessages(library(igraph))

nodes <- read.csv(nodes_path, stringsAsFactors = FALSE, check.names = FALSE)
edges <- read.csv(edges_path, stringsAsFactors = FALSE, check.names = FALSE)

required_nodes <- c("id", "label", "node_type")
required_edges <- c("source", "target")
if (!all(required_nodes %in% names(nodes))) stop("nodes.csv missing required columns")
if (!all(required_edges %in% names(edges))) stop("edges.csv missing required columns")

g <- graph_from_data_frame(edges, directed = any(edges$directed %in% c(TRUE, "True", "true", "1")), vertices = nodes)

pdf(out_path, width = 10, height = 8)
plot(
  g,
  vertex.label = V(g)$label,
  vertex.size = 8,
  edge.arrow.size = 0.35,
  main = "Discourse network (layout is presentation, not theoretical distance)"
)
mtext("Safeguard: community/centrality/degree are descriptive network properties, not ideological formations, hegemony, or nodal points.", side = 1, line = 4, cex = 0.7)
dev.off()
