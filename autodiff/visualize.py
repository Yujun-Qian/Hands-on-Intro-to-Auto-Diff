import matplotlib.pyplot as plt
from matplotlib import animation, rc
from matplotlib.lines import Line2D
import matplotlib.gridspec as gridspec
import networkx as nx
from networkx.classes import graph
from compgraph.nodes import *
from collections import defaultdict
import autodiff.grads as grads
import numpy as np

def _sweep_graph(node):
    """
    performs a backward sweep of the graph of the given node to build the nx
    graph object and collect relevant info to the visualization

    Parameters:
    ----------
    node: Node
        the node to sweep its computational graph
    """

    leafs_count = 0
    name_to_node = {}
    var_node_names = []
    color_dict = {'VariableNode': 'lightblue', 'ConstantNode': 'orange'}
    color = lambda n: color_dict[n.__class__.__name__] if n.__class__.__name__ in color_dict else '#d5a6f9'

    queue = NodesQueue()
    G = nx.DiGraph(graph={'rankdir': 'LR'})

    queue.push(node)
    G.add_node(node.name, label=f"${node.name}$", color=color(node))

    while len(queue) > 0:
        current = queue.pop()
        name_to_node[current.name] = current
        if isinstance(current, VariableNode) or isinstance(current, ConstantNode):
            if isinstance(current, VariableNode):
                var_node_names.append(current.name)
            if current not in queue:
                leafs_count += 1
            continue
        else:

            previous_nodes = sorted(
                filter(lambda n: n is not None, [current.operand_a, current.operand_b]),
                key=lambda n: n.name
            )

            for prev_node in previous_nodes:
                if prev_node is not None:
                    G.add_node(prev_node.name, label=f"${prev_node.name}$", color=color(prev_node))
                    G.add_edge(prev_node.name, current.name)

                    if prev_node not in queue:
                        queue.push(prev_node)

    return G, leafs_count, var_node_names, name_to_node


def visualize_AD(node, figsize=None):
    """
    craetes a matplotlib animation visualizing the reverse AD process on the
    the computational graph of the given node

    Parameters:
    ----------
    node: Node
        the node to visualize the reverse AD process on its computational graph
    """

    nx_graph, leafs_count, var_names, name_to_node = _sweep_graph(node)
    frames_count = len(nx_graph.edges()) + leafs_count

    edge_labels = {}

    # set the stage for the visualization
    fig = plt.figure(figsize=figsize)
    gs = gridspec.GridSpec(3, 1, hspace=0, wspace=0)

    graph_ax = plt.subplot(gs[0:2, 0])
    chain_ax = plt.subplot(gs[2:3, 0])

    chain_ax.axis("off")
    chain_txt = chain_ax.text(0.2, 0.5, '', fontsize=25, va='center', fontfamily='serif')

    # set the necessary data strutures fro reverse AD
    adjoint = defaultdict(int)
    parameters_dict = {
        'var_names': var_names,
        'nx_graph': nx_graph,
        'adjoint': defaultdict(int),
        'display_adjoint': defaultdict(int),
        'queue': NodesQueue(),
        'current_node': None,
        'other_operand': False,  # true if the next call of animate is handeling operand_b
        'grads_annotations': {}
    }
    parameters_dict['adjoint'][node.name] = ConstantNode.create_using(np.ones(node.shape))
    parameters_dict['queue'].push(node)

    def node_grad(node, index):
        """
        returns a string containing the local grad of a node

        Parameters:
        ----------
        node: Node
            the node to print its local grad
        index: int
            the index of the operand to get the grad wrt
        """

        local_grad_txt = ""

        if node.opname == 'add':
            local_grad_txt += "$%s = %s + %s \Rightarrow \\frac{\partial %s}{\partial %s} = 1$" % (
                node.name, node.operand_a.name, node.operand_b.name, node.name,
                node.operand_a.name if index == 0 else node.operand_b.name
            )
        elif node.opname == 'sub':
            local_grad_txt += "$%s = %s - %s \Rightarrow \\frac{\partial %s}{\partial %s} = %s1$" % (
                node.name, node.operand_a.name, node.operand_b.name, node.name,
                node.operand_a.name if index == 0 else node.operand_b.name,
                "" if indx == 0 else "-"
            )
        elif node.opname == 'mul':
            local_grad_txt += "$%s = %s \\times %s \Rightarrow \\frac{\partial %s}{\partial %s} = %s = %.4s$" % (
                node.name, node.operand_a.name, node.operand_b.name, node.name,
                node.operand_a.name if index == 0 else node.operand_b.name,
                node.operand_b.name if index == 0 else node.operand_a.name,
                node.operand_b if index == 0 else node.operand_a
            )
        elif node.opname == 'div':
            local_grad_txt += "$%s = \\frac{%s}{%s} \Rightarrow \\frac{\partial %s}{\partial %s} =" % (
                node.name, node.operand_a.name, node.operand_b.name, node.name,
                node.operand_a.name if index == 0 else node.operand_b.name
            )
            if index == 0:
                local_grad_txt += "\\frac{1}{%s} = %.4s$" % (node.operand_b.name, 1 / node.operand_b)
            else:
                local_grad_txt += "-\\frac{%s}{%s^2} = %.4s$" % (
                    node.operand_a.name, node.operand_b.name, -1 * node.operand_a / (node.operand_b **2)
                )
        elif node.opname == 'pow':
            local_grad_txt += "$%s = %s^{%s} \Rightarrow \\frac{\partial %s}{\partial %s} =" % (
                node.name, node.operand_a.name, node.operand_b.name, node.name,
                node.operand_a.name if index == 0 else node.operand_b.name
            )
            if index == 0:
                local_grad_txt += "%s \\times %s^{%s - 1} = %.4s$" % (
                    node.operand_b.name, node.operand_a.name, node.operand_b.name,
                    node.operand_b * (node.operand_a ** (node.operand_b - 1))
                )
            else:
                local_grad_txt += "%s^{%s}\ln %s = %.4s$" % (
                    node.operand_a.name, node.operand_b.name, node.operand_a.name,
                    node * np.log(node.operand_a)
                )
        elif node.opname == 'sin':
            local_grad_txt += "$%s = \sin(%s) \Rightarrow \\frac{\partial %s}{\partial %s} = \cos(%s) = %.4s$" % (
                node.name, node.operand_a.name, node.name, node.operand_a.name, node.operand_a.name,
                np.cos(node.operand_a)
            )
        elif node.opname == 'cos':
            local_grad_txt += "$%s = \cos(%s) \Rightarrow \\frac{\partial %s}{\partial %s} = -\sin(%s) = %.4s$" % (
                node.name, node.operand_a.name, node.name, node.operand_a.name, node.operand_a.name,
                -1 * np.sin(node.operand_a)
            )
        elif node.opname == 'exp':
            local_grad_txt += "$%s = \exp(%s) \Rightarrow \\frac{\partial %s}{\partial %s} = \exp(%s) = %.4s$" % (
                node.name, node.operand_a.name, node.name, node.operand_a.name, node.operand_a.name,
                node
            )
        elif node.opname == 'log':
            local_grad_txt += "$%s = \ln(%s) \Rightarrow \\frac{\partial %s}{\partial %s} = \\frac{1}{%s} = %.4s$" % (
                node.name, node.operand_a.name, node.name, node.operand_a.name, node.operand_a.name,
                1. / node.operand_a
            )
        return local_grad_txt

    def process_edge(current, prev, indx, params):
        """
        performs the necessary processing for an edge between current and prev
        nodes

        Parameters:
        ----------
        current: Node
            the current node passinf it's adjoint
        prev: Node
            the operand node that its adjoint being calculated
        indx: int
            the index of the operand node
        """

        if isinstance(prev, ConstantNode):
           return "Constant operand\nNo derivatives to propagate"

        current_adjoint = params['adjoint'][current.name]
        current_op = current.opname

        op_grad = getattr(grads, '%s_grad' % (current_op))
        next_adjoints = op_grad(current_adjoint, current)

        gradient = 0
        if next_adjoints[indx] != 0:
            gradient = next_adjoints[indx] / current_adjoint

        params['adjoint'][prev.name] = params['adjoint'][prev.name] + next_adjoints[indx]
        params['display_adjoint'][(prev.name, current.name)] = gradient

        chain_txt = ""

        chain_txt += node_grad(current, indx) + "\n"
        chain_txt += "$\\frac{\partial f}{\partial %s} \/ += \/ \\frac{\partial f}{\partial %s}\\frac{\partial %s}{\partial %s} = %.4s\\times%.4s=%.4s$" % (
                prev.name,
                current.name,
                current.name,
                prev.name,
                current_adjoint,
                next_adjoints[indx] / current_adjoint,
                next_adjoints[indx]
        )

        return chain_txt


    def update_edge_labels(params):
        edge_labels = {}
        graph = params.get("nx_graph")
        adjoints = params.get("adjoint")
        display_adjoints = params.get("display_adjoint")

        for node in graph.nodes():
            if node in adjoints:
                actual_node = name_to_node.get(node)
                if isinstance(actual_node, VariableNode) or isinstance(actual_node, ConstantNode):
                    continue
                if not isinstance(actual_node.operand_a, ConstantNode):
                    edge_labels[(actual_node.operand_a.name, actual_node.name)] = "$%.4s$" % (display_adjoints.get((actual_node.operand_a.name, actual_node.name)))
                if actual_node.operand_b is not None and not isinstance(actual_node.operand_b, ConstantNode):
                    edge_labels[(actual_node.operand_b.name, actual_node.name)] = "$%.4s$" % (display_adjoints.get((actual_node.operand_b.name, actual_node.name)))

        return edge_labels


    def update_figure(params, chain_txt_buff="", edge_labels={}):
        """
        performs the necessary updates to the axes to craete the frame
        """

        graph_ax.clear()

        #legend

        op_circle = Line2D([0], [0], marker='o', color='w', label='Operational Node', markerfacecolor='#d5a6f9', markersize=15)
        const_circle = Line2D([0], [0], marker='o', color='w', label='Constant Node', markerfacecolor='orange', markersize=15)
        var_circle = Line2D([0], [0], marker='o', color='w', label='Variable Node', markerfacecolor='lightblue', markersize=15)

        graph_ax.legend(handles=[op_circle, var_circle, const_circle])

        node_colors = []
        node_labels = {}
        node_boundary_colors = []
        node_boundary_thickness = []
        edges_colors = []
        edges_widths = []


        for _node in params['nx_graph'].nodes(data=True):
            node_labels[_node[0]] = _node[1]['label']
            if _node[0] == params['current_node'].name:
                node_boundary_colors.append("#45a325")
                node_boundary_thickness.append(5)
            else:
                node_boundary_colors.append('black')
                node_boundary_thickness.append(1)

            node_colors.append(_node[1]['color'])

        for _edge in params['nx_graph'].edges():
            if _edge == params['current_edge']:
                edges_colors.append("#45a325")
                edges_widths.append(5)
            else:
                edges_colors.append("black")
                edges_widths.append(1)

        pos=nx.nx_pydot.pydot_layout(params['nx_graph'], prog='dot')

        nx.draw(
            params['nx_graph'], pos, ax=graph_ax, 
            arrows=True, node_color=node_colors, node_size=2000, 
            edgecolors=node_boundary_colors, linewidths=node_boundary_thickness,
            edge_color=edges_colors, width=edges_widths
        )
        nx.draw_networkx_labels(params['nx_graph'], pos, ax=graph_ax, labels=node_labels, font_size=15)
        nx.draw_networkx_edge_labels(params['nx_graph'], pos, ax=graph_ax, edge_labels=edge_labels, bbox={'boxstyle':'square,pad=0.1', 'fc':'white', 'ec':'white'}, font_size=18, font_color='slategray', font_weight="bold", label_pos=0.65)
        for variable in params['var_names']:
            if variable in params['grads_annotations']:
                params['grads_annotations'][variable].remove()
            node_pos = pos[variable]
            d_txt = "$\\frac{\partial f}{\partial %s} = %.4s$" % (variable, params['adjoint'][variable])
            ant = graph_ax.annotate(d_txt, xy=node_pos, xytext=(-100, 0), textcoords='offset points', size=20, ha='center', va='center')
            params['grads_annotations'][variable] = ant
        chain_txt.set_text(chain_txt_buff)

    def init_func():
        return []

    def animate(i, params):
        """
        sets the content of each frame of the animation
        """

        chain_txt_buff = ""
        edge_labels = update_edge_labels(params)

        if len(params['queue']) > 0 and not params['other_operand']:
            params['current_node'] = params['queue'].pop()
            current_node = params['current_node']

            if isinstance(current_node, ConstantNode):
                update_figure(params, "Constant node → End of path", edge_labels)
                return []
            if isinstance(current_node, VariableNode):
                update_figure(params, "Variable node → End of path", edge_labels)
                return []

            params['current_edge'] = (current_node.operand_a.name, current_node.name)

            chain_txt_buff = process_edge(current_node, current_node.operand_a, 0, params)
            
            #if not isinstance(current_node.operand_a, ConstantNode):
                #edge_labels[(current_node.operand_a.name, current_node.name)] = "$\\frac{\partial f}{\partial %s} = %.4s$" % (current_node.name, params['adjoint'][current_node.name])

            if current_node.operand_a not in params['queue']:
                params['queue'].push(current_node.operand_a)

            if current_node.operand_b is not None:
                params['other_operand'] = True
            else:
                params['adjoint'][current_node.name] = 0
        elif len(params['queue']) > 0:
            current_node = params['current_node']
            params['current_edge'] = (current_node.operand_b.name, current_node.name)

            chain_txt_buff = process_edge(current_node, current_node.operand_b, 1, params)
            #if not isinstance(current_node.operand_b, ConstantNode):
                #edge_labels[(current_node.operand_b.name, current_node.name)] = "$\\frac{\partial f}{\partial %s} = %.4s$" % (current_node.name, params['adjoint'][current_node.name])

            if current_node.operand_b not in params['queue']:
                params['queue'].push(current_node.operand_b)

            params['other_operand'] = False  # reset the flag after processing
            params['adjoint'][current_node.name] = 0
        else:
            return []

        edge_labels = update_edge_labels(params)

        update_figure(params, chain_txt_buff, edge_labels)
        params['current_edge'] = None

        return []

    rc('animation', html='html5')
    rc("mathtext", fontset='cm')
    return animation.FuncAnimation(
        fig, animate, init_func=init_func,
        frames=frames_count, interval=2500,
        fargs=[parameters_dict]
    )
