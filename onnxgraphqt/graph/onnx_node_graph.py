from dataclasses import dataclass
from typing import (
    Dict, List, Any, Optional, Union
)
from collections import OrderedDict
import copy
import NodeGraphQt

import numpy as np
import onnx
import onnx_graphsurgeon as gs
import igraph

from PySide2 import QtCore, QtWidgets
from NodeGraphQt.constants import (
    NODE_LAYOUT_HORIZONTAL,
    NODE_LAYOUT_VERTICAL,
    ViewerEnum,
)
from NodeGraphQt.base import node, graph
from NodeGraphQt.qgraphics import pipe
node.NODE_LAYOUT_DIRECTION = NODE_LAYOUT_VERTICAL
graph.NODE_LAYOUT_DIRECTION = NODE_LAYOUT_VERTICAL
pipe.NODE_LAYOUT_DIRECTION = NODE_LAYOUT_VERTICAL

from NodeGraphQt import NodeGraph, BaseNode
from NodeGraphQt.base.node import NodeObject
from NodeGraphQt.base.factory import NodeFactory
from NodeGraphQt.base.model import NodeGraphModel
from NodeGraphQt.widgets.viewer import NodeViewer

import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from utils.color import (
    COLOR_BG,
    COLOR_FONT,
    COLOR_GRID,
    COLOR_WHITE,
    COLOR_GRAY,
    INPUT_NODE_COLOR,
    OUTPUT_NODE_COLOR,
    get_node_color,
    PrintColor,
)
from utils.dtype import (
    DTYPES_TO_NUMPY_TYPES,
)
from utils.style import set_context_menu_style
from utils.widgets import pipe_paint
from .onnx_node import (
    ONNXInput,
    ONNXOutput,
    ONNXNode,
    OnnxNodeIO
)

NUMPY_TYPES_TO_ONNX_DTYPES = {
    np.dtype('float32'): onnx.TensorProto.FLOAT,
    np.dtype('float64'): onnx.TensorProto.DOUBLE,
    np.dtype('int32'): onnx.TensorProto.INT32,
    np.dtype('int64'): onnx.TensorProto.INT64,
}

NAME = str
@dataclass
class OnnxGraph:
    inputs: Dict[NAME, ONNXInput]
    outputs: Dict[NAME, ONNXOutput]
    nodes: Dict[NAME, ONNXNode]
    node_inputs: Dict[NAME, OnnxNodeIO]

class ONNXNodeGraph(NodeGraph):
    def __super__init__(self, parent=None, **kwargs):
        """
        Args:
            parent (object): object parent.
            **kwargs (dict): Used for overriding internal objects at init time.
        """
        super(NodeGraph, self).__init__(parent)
        self.setObjectName('NodeGraph')
        self._model = (
            kwargs.get('model') or NodeGraphModel())
        self._node_factory = (
            kwargs.get('node_factory') or NodeFactory())

        self._undo_view = None
        self._undo_stack = (
            kwargs.get('undo_stack') or QtWidgets.QUndoStack(self))

        self._widget = None

        self._sub_graphs = {}

        self._viewer = (
            kwargs.get('viewer') or NodeViewer(undo_stack=self._undo_stack))

        # self._build_context_menu()
        # self._register_builtin_nodes()
        self._wire_signals()

    def __init__(self, name: str, opset: int, doc_string: str, import_domains: str,
                 producer_name: str, producer_version: str, ir_version: int, model_version: int,
                 parent=None, **kwargs):
        self.__super__init__(parent, **kwargs)
        self.name = name
        self.opset = opset
        self.doc_string = doc_string
        self.import_domains = import_domains
        self.producer_name = producer_name
        self.producer_version = producer_version
        self.ir_version = ir_version
        self.model_version = model_version
        self.register_nodes([
            ONNXNode,
            ONNXInput,
            ONNXOutput,
        ])
        self.set_background_color(*COLOR_BG)
        self.set_grid_mode(ViewerEnum.GRID_DISPLAY_DOTS)
        self.set_grid_color(*COLOR_GRID)
        set_context_menu_style(self, text_color=COLOR_FONT, bg_color=COLOR_WHITE, selected_color=COLOR_GRAY)
        # # Disable right click menu
        # self.disable_context_menu(True)

    def reset_selection(self):
        for node in self.all_nodes():
            # node.set_selected(False)
            node.set_property("selected", False, push_undo=False)

    def fit_to_selection_node(self, node):
        self.reset_selection()
        # node.set_selected(True)
        node.set_property("selected", True, push_undo=False)
        self.fit_to_selection()

    def get_selected_node_names(self)->List[str]:
        return [node.name() for node in self.all_nodes() if node.selected()]

    def get_node_by_name(self, name)->List[Union[ONNXInput, ONNXOutput, ONNXNode]]:
        """
        Returns node that matches the name.

        Args:
            name (str): name of the node.
        Returns:
            NodeGraphQt.NodeObject: node object.
        """
        ret = []
        for node_id, node in self._model.nodes.items():
            if isinstance(node, ONNXNode):
                if node.node_name == name:
                    ret.append(node)
            if node.name() == name:
                ret.append(node)
        return ret

    def remove_all_nodes(self, push_undo=False):
        for node in self.all_nodes():
            for p in node.input_ports():
                p.set_locked(state=False, push_undo=push_undo)
            for p in node.input_ports():
                p.clear_connections(push_undo=push_undo)

            for p in node.output_ports():
                p.set_locked(state=False, push_undo=push_undo)
            for p in node.output_ports():
                p.clear_connections(push_undo=push_undo)

            self.remove_node(node, push_undo=push_undo)

    def _serialize(self, nodes)->Dict[str, Any]:
        ret = super()._serialize(nodes)
        ret['graph']['name'] = self.name
        ret['graph']['opset'] = self.opset
        ret['graph']['doc_string'] = self.doc_string
        return ret

    def _deserialize(self, data, relative_pos=False, pos=None):
        ret = super()._deserialize(data, relative_pos, pos)
        self.name = data['graph']['name']
        self.opset = data['graph']['opset']
        self.doc_string = data['graph']['doc_string']
        return ret

    def node_count(self)->int:
        return len(self.all_nodes())

    def create_qtinput(self, input: gs.Tensor, push_undo=False)->ONNXInput:
        node_name = input.name
        n = self.create_node("nodes.node.ONNXInput", node_name, push_undo=push_undo)
        n.set_node_name(node_name)
        n.set_shape(copy.deepcopy(input.shape))
        n.set_dtype(input.dtype)
        n.set_output_names([o.name for o in input.outputs])
        n.set_color()
        return n

    def create_qtoutput(self, output: gs.Tensor, push_undo=False)->ONNXOutput:
        node_name = output.name
        n = self.create_node("nodes.node.ONNXOutput", node_name, push_undo=push_undo)
        n.set_node_name(node_name)
        n.set_shape(copy.deepcopy(output.shape))
        n.set_dtype(output.dtype)
        n.set_input_names([i.name for i in output.inputs])
        n.set_color()
        return n

    def create_qtnode(self, onnx_node: gs.Node, push_undo=False)->NodeObject:
        node_name = onnx_node.name # str
        n = self.create_node("nodes.node.ONNXNode", name=node_name, push_undo=push_undo)
        onnx_inputs:List[OnnxNodeIO] = []
        for inp in onnx_node.inputs:
            t = type(inp)
            if t is gs.Tensor:
                onnx_inputs += [OnnxNodeIO(inp.name, str(inp.dtype), inp.shape, None)]
            elif t is gs.Constant:
                onnx_inputs += [OnnxNodeIO(inp.name, str(inp.values.dtype), inp.shape, inp.values.tolist())]
            elif t is gs.Variable:
                if inp.dtype is None:
                    onnx_inputs += [OnnxNodeIO(inp.name, None, None, None)]
                else:
                    onnx_inputs += [OnnxNodeIO(inp.name, str(inp.dtype), inp.shape, None)]
            else:
                onnx_inputs += [OnnxNodeIO(inp.name, None, None, None)]
        onnx_outputs = []
        for out in onnx_node.outputs:
            t = type(out)
            if t is gs.Tensor:
                onnx_outputs += [OnnxNodeIO(out.name, str(out._values.dtype), out.shape, None)]
            elif t is gs.Constant:
                onnx_outputs += [OnnxNodeIO(out.name, str(out.values.dtype), out.shape, out.values.tolist())]
            elif t is gs.Variable:
                if out.dtype is None:
                    onnx_outputs += [OnnxNodeIO(out.name, None, None, None)]
                else:
                    onnx_outputs += [OnnxNodeIO(out.name, str(out.dtype), out.shape, None)]
            else:
                onnx_outputs += [OnnxNodeIO(out.name, None, None, None)]
        n.set_node_name(node_name)
        n.set_op(onnx_node.op) # str
        if len(onnx_inputs) > 0:
            n.set_onnx_inputs(onnx_inputs)
        if len(onnx_outputs) > 0:
            n.set_onnx_outputs(onnx_outputs)
        if n.op in ['Constant']:
            d = {
                "dtype": str(onnx_node.attrs["value"].values.dtype),
                "values": onnx_node.attrs["value"].values.tolist()
            }
            n.set_attrs(d)
        else:
            n.set_attrs(copy.deepcopy(onnx_node.attrs)) # OrderedDict

        n.set_color()
        if n.op in ['Constant']:
            n.set_port_deletion_allowed(True)
            n.delete_input(0)
            n.set_port_deletion_allowed(False)
        return n

    def load_onnx_graph(self, onnx_graph, push_undo=False):
        ONNXtoNodeGraph(onnx_graph, self, push_undo=push_undo)

    def to_onnx_gs(self) -> gs.Graph:
        return NodeGraphtoONNX(self)

    def to_onnx(self, non_verbose=True)->onnx.ModelProto:
        graph = self.to_onnx_gs()
        ret = None
        try:
            ret = gs.export_onnx(graph, do_type_check=True)
            ret.producer_name = self.producer_name
            ret.producer_version = self.producer_version
            ret.ir_version = self.ir_version
            ret.model_version = self.model_version
            onnx.checker.check_model(
                model=ret,
                full_check=False
            )
        except BaseException as e:
            if not non_verbose:
                print(e)
        return ret

    def to_data(self)->OnnxGraph:
        inputs = {}
        outputs = {}
        nodes = {}
        node_inputs = {}
        for n in self.all_nodes():
            if isinstance(n, ONNXNode):
                nodes[n.name()] = n
                for inp in n.onnx_inputs:
                    node_inputs[inp.name] = inp
            elif isinstance(n, ONNXInput):
                inputs[n.name()] = n
            elif isinstance(n, ONNXOutput):
                outputs[n.name()] = n
        return OnnxGraph(inputs=inputs, outputs=outputs, nodes=nodes, node_inputs=node_inputs)


    def export(self, file_path:str):
        try:
            onnx.save(self.to_onnx(), file_path)
            # from onnx_graphsurgeon.exporters.onnx_exporter import OnnxExporter
            # og = OnnxExporter.export_graph(self.to_onnx_gs(), do_type_check=True)
            # opset_imports = [onnx.helper.make_opsetid("", self.opset)]
            # single_op_graph = make_model(og, opset_imports=opset_imports)
        except Exception as e:
            raise e

    def auto_layout(self, push_undo=True):
        auto_layout_nodes(self, push_undo=push_undo)

    def update_pipe_paint(self):
        nodes = self.all_nodes()
        for node in nodes:
            if isinstance(node, ONNXNode):
                pipes = node.output_port.view.connected_pipes
                for pipe in pipes:
                    def paint(pipe, text):
                        def func(painter, option, widget):
                            return pipe_paint(pipe, painter, option, widget, text)
                        return func
                    attrs = node.get_attrs()
                    pipe.paint = paint(pipe, f"")
            if isinstance(node, ONNXInput):
                pipes = node.output_port.view.connected_pipes
                for pipe in pipes:
                    def paint(pipe, text):
                        def func(painter, option, widget):
                            return pipe_paint(pipe, painter, option, widget, text)
                        return func
                    pipe.paint = paint(pipe, f"{node.get_shape()}")

def NodeGraphToEdges(graph:ONNXNodeGraph, reverse=True)->List:
    ret = []
    if reverse:
        node_names = [n.name() for n in graph.all_nodes()[::-1]]
        for i, n in enumerate(graph.all_nodes()[::-1]):
            for input_nodes in n.connected_input_nodes().values():
                for inp in input_nodes:
                    input_index = node_names.index(inp.name())
                    ret.append([i, input_index])
    else:
        node_names = [n.name() for n in graph.all_nodes()]
        for i, n in enumerate(graph.all_nodes()):
            for input_nodes in n.connected_input_nodes().values():
                for inp in input_nodes:
                    input_index = node_names.index(inp.name())
                    ret.append([input_index, i])
    return ret


def NodeGraphtoONNX(graph: ONNXNodeGraph) -> gs.Graph:
    input_names = []
    output_names = []
    input_variables = []
    output_variables = []
    gs_variables_all = {}

    for n in graph.get_nodes_by_type("nodes.node.ONNXInput"):
        v = gs.Variable(name=n.name(), dtype=n.get_dtype(), shape=n.get_shape())
        input_variables.append(v)
        input_names.append(n.name())
        gs_variables_all[n.name()] = v

    for n in graph.get_nodes_by_type("nodes.node.ONNXOutput"):
        v = gs.Variable(name=n.name(), dtype=n.get_dtype(), shape=n.get_shape())
        output_variables.append(v)
        output_names.append(n.name())
        gs_variables_all[n.name()] = v

    nodes = []
    for n in graph.get_nodes_by_type("nodes.node.ONNXNode"):
        input_gs_variables = []
        output_gs_variables = []

        for inp in n.onnx_inputs:
            name, dtype, shape, val = inp.name, inp.dtype, inp.shape, inp.values
            if name in gs_variables_all.keys():
                v = gs_variables_all[name]
            elif dtype is None:
                v = gs.Variable(name=name, dtype=None, shape=None)
                gs_variables_all[name] = v
            elif val == -1 or val is None:
                v = gs.Variable(name=name, dtype=dtype, shape=shape)
                gs_variables_all[name] = v
            else:
                v = gs.Constant(name=name, values=np.array(val, dtype=dtype).reshape(shape))
                gs_variables_all[name] = v
            input_gs_variables.append(v)

        for out in n.onnx_outputs:
            name, dtype, shape, val = out.name, out.dtype, out.shape, out.values
            if name in gs_variables_all.keys():
                v = gs_variables_all[name]
            elif dtype is None:
                v = gs.Variable(name=name, dtype=None, shape=None)
                gs_variables_all[name] = v
            elif val == -1 or val is None:
                v = gs.Variable(name=name, dtype=dtype, shape=shape)
                gs_variables_all[name] = v
            else:
                v = gs.Constant(name=name, values=np.array(val, dtype=dtype).reshape(shape))
                gs_variables_all[name] = v
            output_gs_variables.append(v)
        n:ONNXNode
        # 2. Node Generation
        node = None
        value_info = None
        if n.op not in ['Constant', 'ConstantOfShape']:
            # non constant
            node = gs.Node(
                op=n.op,
                name=n.get_node_name(),
                attrs=n.get_attrs(),
                inputs=input_gs_variables,
                outputs=output_gs_variables
            )
        else:
            # constant
            dtype = n.attrs["dtype"]
            dtype = NUMPY_TYPES_TO_ONNX_DTYPES[np.dtype(dtype)]
            attr_values = n.attrs["values"]
            if isinstance(attr_values, list):
                shape = [len(attr_values)]
            elif isinstance(attr_values, np.ndarray):
                shape = attr_values.shape
            else:
                shape = [1]
                attr_values = [attr_values]

            constant_name = [i.name for i in output_gs_variables][0]
            value_info = onnx.helper.make_tensor_value_info(
                constant_name,
                dtype,
                shape
            )
            node = onnx.helper.make_node(
                n.op,
                inputs=[],
                outputs=[constant_name],
                name=n.node_name,
                value=onnx.helper.make_tensor(
                    name='value',
                    data_type=dtype,
                    dims=shape,
                    vals=attr_values,
                ),
            )

        # 3. Graph Generation
        single_op_graph = None
        if n.op not in ['Constant', 'ConstantOfShape']:
            g = gs.Graph(
                nodes=[node],
                inputs=input_gs_variables,
                outputs=output_gs_variables,
                opset=n.op,
            )
            node = g.nodes[0]
        else:
            graph_def = onnx.helper.make_graph(
                nodes=[node],
                name=n.op,
                inputs=[],
                outputs=[value_info],
            )
            single_op_graph = onnx.helper.make_model(graph_def)
            gs_graph = gs.import_onnx(single_op_graph)
            node = gs_graph.nodes[0]

        nodes.append(node)

    onnx_graph = gs.Graph(
        nodes=nodes,
        name=graph.name,
        opset=graph.opset,
        inputs=input_variables,
        outputs=output_variables,
        doc_string=graph.doc_string,
        import_domains=graph.import_domains,
    )
    return onnx_graph

def auto_layout_nodes(graph:ONNXNodeGraph, push_undo=True):
    if push_undo:
        graph.begin_undo('Auto Layout Nodes')

    edges = NodeGraphToEdges(graph, reverse=True)
    if len(edges) == 0:
        return
    ig_graph = igraph.Graph(edges=edges, directed=True)
    layout, _graph = ig_graph.layout_sugiyama(hgap=2, return_extended_graph=True)
    for i, node in enumerate(graph.all_nodes()[::-1]):
        x, y = layout.coords[i]
        node.set_property('pos', [float(-x*240), float(-y*120)], push_undo=push_undo)

    if push_undo:
        graph.end_undo()


def ONNXtoNodeGraph(onnx_graph: gs.Graph, node_graph:ONNXNodeGraph, push_undo=False):
    qt_io_nodes = {}
    qt_io_edge = {}
    qt_nodes = {}
    qt_edge = {}

    # Create Input/Output Node
    for inp in onnx_graph.inputs:
        qt_n = node_graph.create_qtinput(inp, push_undo=push_undo)
        qt_io_nodes[inp.name] = qt_n

    for out in onnx_graph.outputs:
        qt_n = node_graph.create_qtoutput(out, push_undo=push_undo)
        qt_io_nodes[out.name] = qt_n

    # Create Node
    for onnx_node in onnx_graph.nodes:
        qt_n = node_graph.create_qtnode(onnx_node, push_undo=push_undo)
        qt_nodes[onnx_node.name] = qt_n

    for onnx_node in onnx_graph.nodes:
        for input in onnx_node.inputs:
            if input.name not in qt_edge.keys():
                qt_edge[input.name] = {
                    "inputs": [onnx_node.name],
                    "outputs": [],
                }
            else:
                qt_edge[input.name]["inputs"].append(onnx_node.name)
        for output in onnx_node.outputs:
            if output.name not in qt_edge.keys():
                qt_edge[output.name] = {
                    "inputs": [],
                    "outputs": [onnx_node.name],
                }
            else:
                qt_edge[output.name]["outputs"].append(onnx_node.name)

    input_names = [inp.name for inp in onnx_graph.inputs]
    output_names = [out.name for out in onnx_graph.outputs]
    # Connect Node
    for key, val in qt_edge.items():
        node_inputs = val["inputs"]
        node_outputs = val["outputs"]
        if key in input_names:
            for inp in node_inputs:
                # qt_io_nodes[key].set_output(0, qt_nodes[inp].input(0))
                src_port = qt_io_nodes[key].output(0)
                src_port.connect_to(qt_nodes[inp].input(0), push_undo=push_undo)
        if key in output_names:
            for out in node_outputs:
                # qt_nodes[out].set_output(0, qt_io_nodes[key].input(0))
                src_port = qt_nodes[out].output(0)
                src_port.connect_to(qt_io_nodes[key].input(0), push_undo=push_undo)
        for inp in node_inputs:
            for out in node_outputs:
                # qt_nodes[out].set_output(0, qt_nodes[inp].input(0))
                src_port = qt_nodes[out].output(0)
                src_port.connect_to(qt_nodes[inp].input(0), push_undo=push_undo)
    # Lock Node and Port
    for n in node_graph.all_nodes():
        for ip in n.input_ports():
            ip.set_locked(state=True, connected_ports=True, push_undo=push_undo)
        for op in n.output_ports():
            op.set_locked(state=True, connected_ports=True, push_undo=push_undo)

