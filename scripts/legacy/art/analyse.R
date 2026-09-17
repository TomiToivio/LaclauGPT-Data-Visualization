#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) stop("usage: analyse.R <view_model.json> <output_dir>")
if (!requireNamespace("jsonlite", quietly = TRUE)) stop("jsonlite is required")
if (!requireNamespace("ggplot2", quietly = TRUE)) stop("ggplot2 is required")

input <- jsonlite::fromJSON(args[[1]], simplifyDataFrame = TRUE)
outdir <- args[[2]]
dir.create(outdir, recursive = TRUE, showWarnings = FALSE)
edges <- input$concept_edges
stopifnot(input$contract_version == "legacy-view-v1")

if (nrow(edges) > 0) {
  matrix_df <- aggregate(weight ~ country + canonical_term, edges, sum)
  write.csv(matrix_df, file.path(outdir, "art_country_concept_matrix.csv"), row.names = FALSE)
  p <- ggplot2::ggplot(matrix_df, ggplot2::aes(x = canonical_term, y = country, fill = weight)) +
    ggplot2::geom_tile() +
    ggplot2::labs(title = "Country × concept descriptive matrix", x = "Concept", y = "Country") +
    ggplot2::theme_minimal() +
    ggplot2::theme(axis.text.x = ggplot2::element_text(angle = 45, hjust = 1))
  ggplot2::ggsave(file.path(outdir, "art_country_concept_matrix.png"), p, width = 10, height = 6)
}

cat(jsonlite::toJSON(list(contract_version=input$contract_version, edges=nrow(edges), geometry=input$geometry), auto_unbox=TRUE, pretty=TRUE))
