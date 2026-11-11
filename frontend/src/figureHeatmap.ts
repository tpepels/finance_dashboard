/** Load the optional heatmap renderer only with the configurable figure workspace. */
import { use } from 'echarts/core';
import { HeatmapChart } from 'echarts/charts';
import { VisualMapComponent } from 'echarts/components';
use([HeatmapChart, VisualMapComponent]);
