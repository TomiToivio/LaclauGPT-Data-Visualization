args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 4) {
  stop("Usage: Rscript tabular_figure.R input.csv x_column y_column output.pdf [group_column]")
}

input_path <- args[[1]]
x_col <- args[[2]]
y_col <- args[[3]]
out_path <- args[[4]]
group_col <- if (length(args) >= 5) args[[5]] else NA_character_

suppressPackageStartupMessages(library(ggplot2))

data <- read.csv(input_path, stringsAsFactors = FALSE, check.names = FALSE)
if (!(x_col %in% names(data))) stop("x column not found")
if (!(y_col %in% names(data))) stop("y column not found")

mapping <- aes(x = .data[[x_col]], y = .data[[y_col]], group = 1)
if (!is.na(group_col) && group_col %in% names(data)) {
  mapping <- aes(x = .data[[x_col]], y = .data[[y_col]], group = .data[[group_col]], linetype = .data[[group_col]])
}

p <- ggplot(data, mapping) +
  geom_line() +
  geom_point() +
  labs(
    x = x_col,
    y = y_col,
    caption = "Descriptive visualization: prevalence/prominence is not evidence of hegemony."
  )

ggsave(out_path, p, width = 9, height = 5)
